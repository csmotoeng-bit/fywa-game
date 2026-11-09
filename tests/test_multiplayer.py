"""Integration tests: run `python -m unittest discover -s tests -v`.
Requires the normal project dependencies. Starts without the background timer.
"""
import os
import unittest
os.environ.setdefault("FYWA_ASYNC_MODE", "threading")
from app import app
from extensions import socketio
from game_state.rooms import rooms
from routes.party_games import tick_rooms

PALETTE = ['#3b82f6','#22c55e','#ef4444','#f97316']


class MultiplayerTests(unittest.TestCase):
    def setUp(self):
        rooms.clear()
        self.clients = []
        self.sockets = []
        self.ids = []
        for i in range(4):
            client = app.test_client()
            data = {"nickname": f"Player{i}", "colour": PALETTE[i]}
            if i == 0:
                response = client.post("/create", data=data)
                self.code = response.location.rsplit('/', 1)[-1]
            else:
                response = client.post("/join", data={**data, "room_code": self.code})
            self.assertEqual(response.status_code, 302)
            with client.session_transaction() as s:
                self.ids.append(s['player_id'])
            self.clients.append(client)
            socket = socketio.test_client(app, flask_test_client=client)
            self.assertTrue(socket.is_connected())
            socket.emit("hub_join")
            socket.get_received()
            self.sockets.append(socket)
        self.room = rooms[self.code]

    def tearDown(self):
        for s in self.sockets:
            if s.is_connected():
                s.disconnect()
        rooms.clear()

    def select(self, key):
        self.sockets[0].emit('hub_select_game', {'game': key})
        self.assertEqual(self.room['active_game'], key)
        for s in self.sockets:
            s.get_received()

    def start(self):
        self.sockets[0].emit('hub_start')
        for s in self.sockets:
            s.get_received()

    def get_party_view(self, idx):
        self.sockets[idx].emit('party_join')
        events = self.sockets[idx].get_received()
        return [e['args'][0] for e in events if e['name']=='party_state'][-1]

    def test_shared_room_colours_and_game_switching(self):
        self.assertEqual(self.clients[0].get('/room/'+self.code).status_code, 200)
        self.sockets[0].emit('hub_colour', {'colour': PALETTE[1]})
        self.assertNotEqual(self.room['players'][self.ids[0]]['colour'],PALETTE[1])
        self.sockets[0].emit('hub_colour', {'colour': '#a855f7'})
        self.assertEqual(self.room['players'][self.ids[0]]['colour'],'#a855f7')
        self.select('dots')
        self.start()
        self.assertEqual(self.room['party']['phase'],'playing')
        self.select('fyoa')
        self.assertIsNone(self.room['party'])
        self.assertEqual(self.room['state'],'lobby')
        self.assertEqual(len(self.room['players']),4)

    def test_original_fyoa_survives(self):
        self.start()
        self.assertEqual(self.room['state'],'voting')
        self.assertGreater(len(self.room['voting']['options']),0)
        # Every player votes on the same category, starting the original game.
        choice = self.room['voting']['options'][0]
        for s in self.sockets:
            s.emit('vote_category',{'category':choice})
        self.assertEqual(self.room['state'],'playing')
        speaker = self.room['current']['speaker_id']
        self.assertIsNotNone(self.room['current']['topic'])
        for idx, user in enumerate(self.ids):
            self.sockets[idx].emit('fyoa_join_socket')
            views=[x['args'][0] for x in self.sockets[idx].get_received() if x['name']=='game_state']
            self.assertTrue(views)
            self.assertEqual(views[-1]['current']['topic'], self.room['current']['topic'] if user == speaker else None)

    def test_clueless_secret_key_and_guesses(self):
        self.select('clueless'); self.start()
        party=self.room['party']
        spy = party['masters']['0']
        guesser = next(pid for pid in self.ids if self.room['teams'][pid]==0 and pid!=spy)
        spy_view=self.get_party_view(self.ids.index(spy))
        guess_view=self.get_party_view(self.ids.index(guesser))
        self.assertEqual(len([t for t in spy_view['types'] if t is not None]),25)
        self.assertEqual(sum(t is not None for t in guess_view['types']),0)
        current=party['turn'];master=party['masters'][str(current)]
        guesser=next(pid for pid in self.ids if self.room['teams'][pid]==current and pid!=master)
        self.sockets[self.ids.index(master)].emit('party_clue',{'clue':'MAYHEM','count':2})
        self.assertEqual(party['phase'],'guess')
        tile=next(i for i,t in enumerate(party['types']) if t!='assassin')
        self.sockets[self.ids.index(guesser)].emit('party_pick_tile',{'index':tile})
        self.assertIn(tile,party['revealed'])
        if party['phase'] != 'finished':
            other=next(pid for pid in self.ids if self.room['teams'][pid]!=current)
            before=list(party['revealed'])
            self.sockets[self.ids.index(other)].emit('party_pick_tile', {'index':next(i for i in range(25) if i not in before)})
            self.assertEqual(before,party['revealed'])

    def test_dots_private_progress_and_scoring(self):
        self.select('dots'); self.start()
        party=self.room['party']
        self.assertEqual(self.get_party_view(0)['groups'],[])
        self.assertEqual(self.get_party_view(1)['groups'],[])
        for group in range(4):
            indices=[i for i,v in enumerate(party['group_indices']) if v==group]
            self.sockets[0].emit('party_dots_submit', {'indices':indices})
            self.assertEqual(len(party['solved'][self.ids[0]]),group+1)
            if group == 0:
                self.assertEqual(self.get_party_view(1)['groups'],[])
        self.assertEqual(party['phase'],'finished')
        self.assertEqual(party['winner'],self.ids[0])
        self.assertEqual(party['scores'][self.ids[0]],700)
        self.assertEqual(len(self.get_party_view(1)['groups']),4)

    def test_forbidden_buzzer_scoring_and_timer(self):
        self.select('forbidden'); self.start()
        party=self.room['party']
        speaker=party['speaker']
        listener=next(pid for pid in self.ids if pid!=speaker)
        speaker_view=self.get_party_view(self.ids.index(speaker))
        listener_view=self.get_party_view(self.ids.index(listener))
        self.assertEqual(len(speaker_view['card']['forbidden']),5)
        self.assertIsNone(listener_view['card'])
        self.sockets[self.ids.index(listener)].emit('party_buzz')
        self.assertEqual(party['buzzed'],listener)
        self.sockets[self.ids.index(speaker)].emit('party_judge_answer',{'correct':True})
        self.assertEqual(party['phase'],'reveal')
        self.assertEqual(party['scores'][speaker],1)
        self.assertEqual(party['scores'][listener],1)
        party['deadline']=0
        tick_rooms()
        self.assertEqual(party['phase'],'playing')
        self.assertEqual(party['round'],2)
        party['deadline']=0
        tick_rooms()
        self.assertEqual(party['phase'],'reveal')
        self.assertEqual(party['last_result']['outcome'],'timeout')

    def test_host_navigation_does_not_reassign_host(self):
        self.sockets[0].disconnect()
        self.assertEqual(self.room['host_id'],self.ids[0])
        from routes.fyoa import transfer_host_if_needed
        transfer_host_if_needed(self.code)
        self.assertEqual(self.room['host_id'],self.ids[0])
        self.room['host_disconnected_at']-=20
        transfer_host_if_needed(self.code)
        self.assertNotEqual(self.room['host_id'],self.ids[0])


if __name__=='__main__':
    unittest.main()
