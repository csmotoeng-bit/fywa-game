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
        self.assertNotEqual(self.room['players'][self.ids[0]]['colour'], PALETTE[1])
        self.sockets[0].emit('hub_colour', {'colour': '#a855f7'})
        self.assertEqual(self.room['players'][self.ids[0]]['colour'], '#a855f7')
        self.sockets[0].emit('hub_colour', {'colour': '#a7c921'})
        self.assertEqual(self.room['players'][self.ids[0]]['colour'], '#a7c921')
        # Connections is no longer selectable, even from a forged socket event.
        self.sockets[0].emit('hub_select_game', {'game': 'dots'})
        self.assertEqual(self.room['active_game'], 'fyoa')
        self.select('clueless')
        self.start()
        self.assertEqual(self.room['lifecycle'], 'playing')
        self.sockets[0].emit('hub_select_game', {'game': 'fyoa'})
        self.assertEqual(self.room['active_game'], 'clueless')
        self.sockets[0].emit('hub_return')
        self.assertEqual(self.room['active_game'], 'clueless')
        self.assertIsNone(self.room['party'])
        self.assertEqual(self.room['lifecycle'], 'lobby')
        self.assertEqual(len(self.room['players']),4)
        self.assertEqual(self.room['host_id'],self.ids[0])
        self.select('fyoa')

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
        self.assertEqual(party['selected_index'],tile)
        self.assertNotIn(tile,party['revealed'])
        team_view=self.get_party_view(self.ids.index(guesser))
        self.assertEqual(team_view['selected_index'],tile)
        enemy=next(pid for pid in self.ids if self.room['teams'][pid]!=current)
        enemy_view=self.get_party_view(self.ids.index(enemy))
        self.assertIsNone(enemy_view['selected_index'])
        self.assertIsNone(enemy_view['selected_by'])
        old_rev=party['selection_rev']
        self.sockets[self.ids.index(enemy)].emit('party_lock_tile',{'revision':old_rev})
        self.assertEqual(party['revealed'],[])
        self.sockets[self.ids.index(guesser)].emit('party_lock_tile',{'revision':old_rev})
        self.assertIn(tile,party['revealed'])
        self.assertIsNone(party['selected_index'])
        # A stale / duplicate lock cannot reveal a second tile.
        before=list(party['revealed'])
        self.sockets[self.ids.index(guesser)].emit('party_lock_tile',{'revision':old_rev})
        self.assertEqual(before,party['revealed'])

    def test_shared_selection_last_write_wins_without_revealing(self):
        self.select('clueless'); self.start()
        party=self.room['party'];turn=party['turn'];master=party['masters'][str(turn)]
        guessers=[pid for pid in self.ids if self.room['teams'][pid]==turn and pid!=master]
        self.sockets[self.ids.index(master)].emit('party_clue', {'clue':'CHAOS','count':3})
        tile=next(i for i in range(25) if i not in party['revealed'])
        self.sockets[self.ids.index(guessers[0])].emit('party_pick_tile',{'index':tile})
        rev=party['selection_rev']
        # Master sees pending guess but cannot lock in.
        self.assertEqual(self.get_party_view(self.ids.index(master))['selected_index'],tile)
        self.sockets[self.ids.index(master)].emit('party_lock_tile',{'revision':rev})
        self.assertEqual(party['revealed'],[])
        self.sockets[self.ids.index(guessers[0])].emit('party_pick_tile',{'index':(tile+1)%25})
        self.sockets[self.ids.index(guessers[0])].emit('party_lock_tile',{'revision':rev})
        self.assertEqual(party['revealed'],[])
        self.sockets[self.ids.index(guessers[0])].emit('party_lock_tile',{'revision':party['selection_rev']})
        self.assertEqual(len(party['revealed']),1)

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
        tick_rooms()
        self.assertEqual(self.room['host_id'],self.ids[0])
        restored=socketio.test_client(app, flask_test_client=self.clients[0])
        self.sockets[0]=restored
        restored.emit('hub_join')
        self.assertTrue(self.room['players'][self.ids[0]]['connected'])
        self.assertEqual(self.room['host_id'],self.ids[0])

    def test_host_ownership_survives_full_game_lifecycle(self):
        self.select('clueless'); self.start()
        host=self.room['host_id']
        self.sockets[0].emit('hub_return')
        self.assertEqual(self.room['host_id'],host)
        self.assertEqual(self.room['lifecycle'],'lobby')
        self.start()
        self.assertEqual(self.room['host_id'],host)
        self.assertEqual(self.room['lifecycle'],'playing')
        # Force results state as if the game had finished.
        self.room['party']['phase']='finished'
        self.room['lifecycle']='results'
        self.sockets[0].emit('hub_rematch')
        self.assertEqual(self.room['host_id'],host)
        self.assertEqual(self.room['lifecycle'],'playing')
        self.sockets[0].emit('hub_return')
        self.assertEqual(self.room['host_id'],host)
        self.assertEqual(self.room['lifecycle'],'lobby')
        self.assertIsNone(self.room['party'])
        self.assertEqual(len(self.room['players']),4)

    def test_host_transfer_is_explicit_only(self):
        self.sockets[1].emit('hub_transfer_host',{'player_id':self.ids[2]})
        self.assertEqual(self.room['host_id'],self.ids[0])
        self.sockets[0].emit('hub_transfer_host',{'player_id':self.ids[2]})
        self.assertEqual(self.room['host_id'],self.ids[2])
        self.sockets[0].emit('hub_select_game',{'game':'clueless'})
        self.assertEqual(self.room['active_game'],'fyoa')

    def test_ready_up_is_optional_and_enforced_when_enabled(self):
        self.sockets[0].emit('hub_settings',{'ready_required':True})
        self.sockets[0].emit('hub_start')
        self.assertEqual(self.room['lifecycle'],'lobby')
        for socket in self.sockets:
            socket.emit('hub_ready',{'ready':True})
        self.sockets[0].emit('hub_start')
        self.assertEqual(self.room['state'],'voting')
        self.sockets[0].emit('hub_return')
        self.assertEqual(self.room['ready'],{})

    def test_party_pause_freezes_and_resume_restores_time(self):
        self.select('forbidden'); self.start()
        game=self.room['party']
        initial=game['deadline']
        self.sockets[0].emit('hub_pause',{'pause':True})
        self.assertIsNotNone(game['paused_at'])
        game['deadline']=0
        tick_rooms()
        self.assertEqual(game['phase'],'playing')
        game['deadline']=initial
        game['paused_at']-=8
        self.sockets[0].emit('hub_pause',{'pause':False})
        self.assertIsNone(game.get('paused_at'))
        self.assertGreater(game['deadline'],initial+6)

    def test_tv_view_does_not_reveal_secret(self):
        self.select('clueless');self.start()
        from routes.hub import display_view
        public=display_view(self.code)['party']
        self.assertEqual(len(public['words']),25)
        self.assertEqual(public['types'],[None]*25)
        self.assertNotIn('selected_index',public)
        self.assertNotIn('masters',public)
        self.assertEqual(self.clients[1].get('/display/'+self.code).status_code,200)



if __name__=='__main__':
    unittest.main()
