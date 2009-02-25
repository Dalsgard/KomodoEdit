#!/usr/bin/env python
# Copyright (c) 2009 ActiveState Software Inc.
# See the file LICENSE.txt for licensing information.

"""test editorhistory.py"""

import sys
import os
import time
from os.path import dirname, join, abspath, basename, splitext, exists, expanduser
import unittest
from pprint import pprint, pformat

from editorhistory import History, Location, _RecentsDict
try:
    import testlib
except ImportError:
    top_dir = dirname(dirname(dirname(abspath(__file__))))
    sys.path.insert(0, join(top_dir, "util"))
    import testlib
    del sys.path[0]



#---- test cases

class _HistoryTestCase(unittest.TestCase):
    _db_path_ = join(dirname(__file__), "tmp", "history.sqlite")
    #TODO: could try with ":memory:" for RAM testing

    def setUp(self):
        frame = sys._getframe(1)
        meth = frame.f_locals["testMethod"]
        name = meth.__name__
        self._db_path_ = join(dirname(self._db_path_), name+".sqlite")
        
        if not exists(dirname(self._db_path_)):
            os.makedirs(dirname(self._db_path_))
        if exists(self._db_path_):
            os.remove(self._db_path_)
        self.history = History(self._db_path_)

class RecentsDictTestCase(unittest.TestCase):
    def test_one(self):
        d = _RecentsDict(1)
        d["a"] = 1
        d["b"] = 2
        self.assertEqual(len(d), 1)
        self.assertEqual(d["b"], 2)

    def test_two(self):
        d = _RecentsDict(2)
        d["a"] = 1
        d["b"] = 2
        d["c"] = 3
        self.assertEqual(len(d), 2)
        self.assertEqual(d, {'b':2, 'c':3})
        
        d["d"] = 4
        self.assertEqual(len(d), 2)
        self.assertEqual(d, {'c':3, 'd':4})
    
        three = d["c"]  # make this most recent
        d["e"] = 5
        self.assertEqual(len(d), 2)
        self.assertEqual(d, {'c':3, 'e':5})

class LocationTestCase(unittest.TestCase):
    def test_cmp(self):
        a = Location("a.txt", 1, 1)
        b = Location("a.txt", 1, 1)
        c = Location("a.txt", 2, 1)
        d = Location("b.txt", 1, 1)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertNotEqual(a, d)
    

class DatabaseTestCase(_HistoryTestCase):
    def test_version(self):
        db = self.history.db
        version = db.version
        self.assert_(version)
        self.assertEqual(version, db.VERSION)

    def test_meta(self):
        db = self.history.db
        db.set_meta("foo", "bar")
        self.assertEqual(db.get_meta("foo"), "bar")
        db.del_meta("foo")
        self.assertEqual(db.get_meta("foo", "not defined"), "not defined")
        
        # Check for uniqueness (key only used once).
        db.set_meta("mykey", "one")
        db.set_meta("mykey", "two")
        self.assertEqual(db.get_meta("mykey"), "two")
        db.del_meta("mykey")
        self.assertEqual(db.get_meta("mykey", "not defined"), "not defined")

    def test_uri(self):
        # Test out working with the `history_uri` table.
        a = "file:///home/trentm/a.txt"
        b = "file:///home/trentm/b.txt"
        db = self.history.db
        a_id = db.uri_id_from_uri(a)
        b_id = db.uri_id_from_uri(b)
        self.assertEqual(a_id, db.uri_id_from_uri(a))
        self.assertEqual(b_id, db.uri_id_from_uri(b))

    def test_timestamp(self):
        # Test the machinations of the `history_visit.timestamp` field
        # which is using (unfamiliar to me) Julian day stuff as per
        # http://eusqlite.wikispaces.com/dates+and+times
        a = "file:///home/trentm/a.txt"
        db = self.history.db
        loc1 = db.add_loc(Location(a, 1, 1))
        time.sleep(1)
        loc2 = db.add_loc(Location(a, 2, 2))
        time.sleep(1)
        loc3 = db.add_loc(Location(a, 3, 3))
        
        with db.connect() as cu:
            # Get the latest visit.
            cu.execute("""
                SELECT id, datetime(timestamp) FROM history_visit
                ORDER BY timestamp DESC LIMIT 1;
                """)
            row = cu.fetchone()
            self.assertEqual(row[0], loc3.id)
            
            # Get visits in the last 2 seconds (should exclude the first
            # one).
            # http://www.sqlite.org/cvstrac/wiki?p=DateAndTimeFunctions
            cu.execute("""
                SELECT id, datetime(timestamp) FROM history_visit
                WHERE timestamp > julianday('now', '-2.0 seconds');
                """)
            rows = cu.fetchall()
            self.assertEqual(len(rows), 2)
            ids = list(sorted(r[0] for r in rows))
            self.assertEqual(ids, [loc2.id, loc3.id])

    def test_addloc(self):
        a = "file:///home/trentm/a.txt"
        b = "file:///home/trentm/b.txt"
        db = self.history.db
        
        loc1 = db.add_loc(Location(a, 10, 10))
        self.assertNotEqual(loc1.id, None)
        self.assertEqual(loc1.referer_id, None)
        
        loc2 = db.add_loc(Location(b, 20, 20), loc1.id)
        self.assertNotEqual(loc2.id, None)
        self.assertEqual(loc2.referer_id, loc1.id,
            "%r doesn't refer to %r" % (loc2, loc1))

        with db.connect() as cu:
            for loc in [loc1, loc2]:
                cu.execute("SELECT visit_count FROM history_uri WHERE id=?",
                           (loc.uri_id,))
                visit_count = cu.fetchone()[0]
                self.assertEqual(visit_count, 1)

    def _get_visit_count(self, uri):
        db = self.history.db
        with db.connect() as cu:
            uri_id = db.uri_id_from_uri(uri)
            cu.execute("SELECT visit_count FROM history_uri WHERE id=?", (uri_id,))
            return cu.fetchone()[0]

    def test_visit_count(self):
        a = "file:///home/trentm/a.txt"
        b = "file:///home/trentm/b.txt"
        db = self.history.db
        
        loc_a1 = db.add_loc(Location(a, 10, 10))
        db.add_loc(Location(a, 10, 10))
        loc_b1 = db.add_loc(Location(b, 10, 10))
        self.assertEqual(self._get_visit_count(a), 2)
        self.assertEqual(self._get_visit_count(b), 1)

        # Cheat and remove a location (no public DB method for this) to test
        # that the visit_count gets updated.
        with db.connect(True) as cu:
            cu.execute("DELETE FROM history_visit WHERE id=?", (loc_a1.id,))
            cu.execute("DELETE FROM history_visit WHERE id=?", (loc_b1.id,))
        self.assertEqual(self._get_visit_count(a), 1)
        self.assertEqual(self._get_visit_count(b), 0)
    
    def test_obsolete_uri(self):
        db = self.history.db
        
        # Setup test history.
        a = "file:///home/trentm/a.txt"
        b = "file:///home/trentm/b.txt"
        locs = [
            self.history.note_loc(Location(uri, (i+1)*10, 1))
            for i in range(5)
            for uri in [a, b]
        ]
        #self.history.debug_dump_recent_history()

        # Obsolete a URI ...
        actual_a_id = db.uri_id_from_uri(a)
        db.obsolete_uri(a, actual_a_id)
        
        # ... and make sure the DB did what we expected.
        b_id = db.uri_id_from_uri(b, create_if_new=False)
        self.assertNotEqual(b_id, None)
        
        with db.connect() as cu:
            cu.execute("SELECT id, is_obsolete FROM history_uri WHERE uri=?", (a,))
            row = cu.fetchone()
            self.assertEqual(row[0], actual_a_id)
            self.assertEqual(row[1], True)
        
        a_id = db.uri_id_from_uri(a, create_if_new=False)
        self.assertEqual(a_id, None)

        a_id = db.uri_id_from_uri(a)   # should revive the URI row
        self.assertEqual(a_id, actual_a_id)
        with db.connect() as cu:
            cu.execute("SELECT id, is_obsolete FROM history_uri WHERE uri=?", (a,))
            row = cu.fetchone()
            a_id = row[0]
            self.assertEqual(a_id, actual_a_id)
            self.assertEqual(row[1], False)


class HistoryTestCase(_HistoryTestCase):
    def test_simple(self):
        a = "file:///home/trentm/a.txt"
        b = "file:///home/trentm/b.txt"
        loc1 = self.history.note_loc(Location(a, 10, 10))
        loc2 = self.history.note_loc(Location(a, 20, 20))
        loc3 = self.history.note_loc(Location(b, 30, 30))
        loc4 = Location(b, 40, 40) # the current location
        
        # No "forward" visits, i.e. the top item of the stack is the
        # current pos.
        #self.history.debug_dump_recent_history(loc4)
        h = list(self.history.recent_history(loc4))
        self.assertEqual(h[0][0], True)  

        # Go "back".
        loc_back = self.history.go_back(loc4)
        self.assertEqual(loc_back, loc3)

        #self.history.debug_dump_recent_history(curr_loc)
        h = list(self.history.recent_history(loc_back))
        self.assertEqual(h[0][1], loc4) # one "forward" visit
        self.assertEqual(h[1][1], loc3) # the curr location
        self.assertEqual(h[2][1], loc2) # "back" one visit
        self.assertEqual(h[3][1], loc1) # "back" two visits

        # Go "forward".
        loc_fwd = self.history.go_forward(curr_loc=loc_back)
        self.assertEqual(loc_fwd, loc4)

        # No "forward" visits remain.
        #self.history.debug_dump_recent_history(loc_fwd)
        h = list(self.history.recent_history(loc_fwd))
        self.assertEqual(h[0][0], True) 

    @testlib.tag("bug81978")
    def test_remember_curr_place(self):
        # Test whether the curr place in history will be remembered between runs.
        
        # Make some interesting history.
        a = "file:///home/trentm/a.txt"
        b = "file:///home/trentm/current.txt"
        locs = [self.history.note_loc(Location(a, 10 * (i + 1), 0))
                for i in range(10)]
        locs.insert(0, None) # Make locs 1-based
        current_loc = Location(b, 55, 0)
        loc_back = self.history.go_back(current_loc, 4)
        self.assertEqual(loc_back, locs[7])
        
        # Test history before the restart:
        h = list(self.history.recent_history(loc_back))
        for i in range(1, 10):
            self.assertEqual(h[i][1], locs[11 - i])

        # Simulate a restart.
        self.history.close()
        self.history = History(self._db_path_)
        
        h = list(self.history.recent_history(loc_back))
        # Test boundary conditions, then check all in a loop.
        self.assertEqual(h[0][1], current_loc) # 4 fwd
        self.assertEqual(h[1][1], locs[10]) # 3 fwd
        self.assertEqual(h[3][1], locs[8]) # 1 fwd
        self.assertEqual(h[4][1], locs[7]) # here
        self.assertEqual(h[5][1], locs[6]) # 1 back
        h = list(self.history.recent_history(loc_back))
        for i in range(1, 10):
            self.assertEqual(h[i][1], locs[11 - i])

    def test_back_then_fwd(self):
        # See the example in the "When to note a location" section in KD 218
        # with this code sample for the scenario being tested here:
        #   1: def foo():
        #   2:   # a comment
        #   3:   print "hi"
        #   4:
        #   5: foo()
        uri = "file:///home/bob/src/foo.txt"
        
        loc1 = self.history.note_loc(Location("file:///etc/passwd", 10, 4))
        loc2 = self.history.note_loc(Location(uri, 5, 1))  # 2. does goto definition: 1,1

        # 3. arrow down a couple of lines: 3,1
        loc3 = Location(uri, 3, 1)
        #self.history.debug_dump_recent_history(loc3)

        # 4. go "Back" one in the history
        loc4 = self.history.go_back(curr_loc=loc3)
        self.assertEqual(loc4, loc2)
        #self.history.debug_dump_recent_history(loc4)

        # 5. go "Forward" should return us to loc3
        loc5 = self.history.go_forward(loc4)
        #self.history.debug_dump_recent_history(loc5)
        self.assertEqual(loc5, loc3)

        # ... Back/Forward should cycle between those two positions.
        curr_loc = loc5
        for i in range(10):
            curr_loc = self.history.go_back(curr_loc)
            self.assertEqual(curr_loc, loc4)
            curr_loc = self.history.go_forward(curr_loc)
            self.assertEqual(curr_loc, loc5)

    def test_update_referer(self):
        # Test the code path that results in `Database.update_referer_id`
        # being called.
        uri = "file:///home/bob/.bashrc"
        locs = [Location(uri, i*2, 1) for i in range(1, 11)]
        for loc in locs:
            self.history.note_loc(loc)
        curr_loc = Location(uri, 42, 1)
        
        for i in range(3):
            curr_loc = Location(curr_loc.uri, curr_loc.line-1, curr_loc.col)
            curr_loc = self.history.go_back(curr_loc)
            self.assertEqual(curr_loc, locs[-(i+1)])
        #self.history.debug_dump_recent_history(curr_loc)
        last_loc = None
        for is_curr, loc in self.history.recent_history(curr_loc):
            if last_loc:
                self.assertEqual(last_loc.referer_id, loc.id)
            last_loc = loc

    @testlib.tag("depleted")
    def test_depleted_recent_back_visits(self):
        # Test the code path that results in the `History.recent_back_visits`
        # cache being depleted so that it needs to be replenished from the
        # db.
        uri = "file:///home/bob/.bashrc"
        locs = [Location(uri, i*2, 1) for i in range(1, self.history.RECENT_BACK_VISITS_CACHE_LENGTH+10)]
        for loc in locs:
            self.history.note_loc(loc)
        curr_loc = Location(uri, 666, 1)
        #self.history.debug_dump_recent_history(curr_loc)
        
        n_to_deplete = len(self.history.recent_back_visits) \
            - self.history.RECENT_BACK_VISITS_DEPLETION_LENGTH + 5
        for i in range(n_to_deplete):
            curr_loc = self.history.go_back(curr_loc)
            self.assertEqual(curr_loc, locs[-(i+1)])
        #self.history.debug_dump_recent_history(curr_loc)
        
        # Test going back forward.
        for j in range(min(n_to_deplete, 20)):
            curr_loc = self.history.go_forward(curr_loc)
            self.assertEqual(curr_loc, locs[-(i-j)])

    @testlib.tag("bug81979")
    def test_forward_visits_integrity_on_multi_step_moves(self):
        uri =         "file:///home/tester/a.txt"
        uri_current = "file:///home/tester/current.txt"
        num_items_to_create = 20
        locs = [self.history.note_loc(Location(uri, i + 1, 0))
                for i in range(num_items_to_create)]
        locs.insert(0, None) # Simplify code, since we're 1-based
            
        first_current_loc = current_loc = Location(uri_current, num_items_to_create + 1, 0)
        locs.append(first_current_loc)
        jump_count = 10
        loc = self.history.go_back(current_loc, jump_count)
        current_loc = loc
        # "Flat" test on individual items at boundaries.
        # If one of these tests fails, it's easy to determine which.
        self.assertEqual(current_loc,
                         locs[num_items_to_create - jump_count + 1])
        self.assertEqual(self.history.forward_visits[-1],
                         locs[num_items_to_create - jump_count + 2])
        self.assertEqual(self.history.forward_visits[1],
                         locs[num_items_to_create])
        self.assertEqual(self.history.forward_visits[0],
                         first_current_loc)
        # Loop through to verify we found everything.
        # If one of these fails, we'll need to uncomment the
        # debug line to figure out what went wrong.
        #self.history.debug_dump_recent_history(curr_loc)
        for i in range(jump_count):
            self.assertEqual(self.history.forward_visits[i],
                             locs[num_items_to_create - i + 1])
        
        # Verify we don't lose the current spot when we move forward.
        jump_count = 4
        old_cid = current_loc.id # 11
        loc = self.history.go_forward(current_loc, jump_count)
        current_loc = loc
        self.assertEqual(current_loc,
                         locs[old_cid + jump_count])
        # Don't roll this loop -- if one of the tests fail, it's
        # harder to determine which one failed
        self.assertEqual(self.history.recent_back_visits[0],
                         locs[old_cid + jump_count - 1])
        self.assertEqual(self.history.recent_back_visits[1],
                         locs[old_cid + jump_count - 2])
        self.assertEqual(self.history.recent_back_visits[2],
                         locs[old_cid + jump_count - 3])
        self.assertEqual(self.history.recent_back_visits[3],
                         locs[old_cid + jump_count - 4])
     
    @testlib.tag("bug81987")
    def test_curr_loc_is_jump_back_loc(self):
        # Test the behaviour when we go_back to a loc that happens to be the
        # same as the current location.
        #
        # The bug is/was that a new location was being added to the history
        # db, rather than just re-using the one to which we are jumping.
        #
        # Note that going forward seems to be fine.
        
        # Setup starter recent history.
        a = "file:///home/tester/a.txt"
        locs = [self.history.note_loc(Location(a, (i+1)*10, 1))
                for i in range(10)]
        curr_loc = Location(a, locs[-1].line, locs[-1].col)     # haven't moved
        #self.history.debug_dump_recent_history(curr_loc, merge_curr_loc=False)
    
        # Test going back one: verify we don't go anywhere.
        new_loc = self.history.go_back(curr_loc, 1)
        #self.history.debug_dump_recent_history(new_loc, merge_curr_loc=False)
        self.assertEqual(len(self.history.forward_visits), 1)
        self.assertEqual(self.history.forward_visits[0], new_loc)

class ObsoleteURITestCase(_HistoryTestCase):
    """
    This testcase is not obsolete!!!
    These tests exercise marking a visited URI obsolete, removing it,
    and correctly setting a new state for the history cache.
    """
    
    @testlib.tag("bug81939")
    def test_obsolete_locs_removed(self):
        uri_stable = "file:///home/tester/stable.txt"
        uri_volatile = "file:///home/tester/volatile.txt"
        uri_current = "file:///home/tester/current.txt"
        # Create 50 entries in the database, every 3rd is the volatile URI
        num_items_to_create = 50
        volatile_factor = 3
        uris = [uri_stable, uri_stable, uri_volatile]
        for i in range(num_items_to_create):
            self.history.note_loc(Location(uris[i % volatile_factor],
                                               10 * (i + 1), 0))
        current_loc = Location(uri_current, num_items_to_create + 1, 0)
        loc = self.history.go_back(current_loc, 3)
        self.assertEqual(loc.uri, uri_volatile)
        self.assertEqual(loc.line, 480)
        self.history.obsolete_uri(loc.uri, 1) # => #490
        v = list(self.history.recent_history(current_loc))
        volatile_locs = [x for x in v if x[1].uri == uri_volatile]
        self.assertEqual(len(volatile_locs), 0)

    @testlib.tag("bug81939")
    def test_move_back(self):
        uri_stable = "file:///home/tester/stable.txt"
        uri_volatile = "file:///home/tester/volatile.txt"
        uri_current = "file:///home/tester/current.txt"
        self.history.note_loc(Location(uri_stable, 10, 0))
        self.history.note_loc(Location(uri_stable, 20, 0))
        self.history.note_loc(Location(uri_volatile, 30, 0))
        self.history.note_loc(Location(uri_stable, 40, 0))
        self.history.note_loc(Location(uri_stable, 50, 0))
        current_loc = Location(uri_current, 100, 0)
        loc = self.history.go_back(current_loc, 2)
        self.assertEqual(loc.line, 40)
        current_loc = loc
        loc = self.history.go_back(current_loc, 1)
        self.assertEqual(loc.line, 30)
        #self.history.debug_dump_recent_history(loc)
        self.history.obsolete_uri(loc.uri, 1) # => #40
        #self.history.debug_dump_recent_history(None)
        loc = self.history.go_back(current_loc, 1)
        self.assertEqual(loc.line, 20)
        
    @testlib.tag("bug81939")
    def test_move_forward(self):
        uri_stable = "file:///home/tester/stable.txt"
        uri_volatile = "file:///home/tester/volatile.txt"
        uri_current = "file:///home/tester/current.txt"
        self.history.note_loc(Location(uri_stable, 10, 0))
        self.history.note_loc(Location(uri_stable, 20, 0))
        self.history.note_loc(Location(uri_volatile, 30, 0))
        self.history.note_loc(Location(uri_stable, 40, 0))
        self.history.note_loc(Location(uri_stable, 50, 0))
        current_loc = Location(uri_current, 100, 0)
        loc = self.history.go_back(current_loc, 4)
        self.assertEqual(loc.line, 20)
        current_loc = loc
        loc = self.history.go_forward(current_loc, 1)
        self.assertEqual(loc.line, 30)
        #self.history.debug_dump_recent_history(loc)
        self.history.obsolete_uri(loc.uri, 1, False) # => #20
        #self.history.debug_dump_recent_history(current_loc)
        loc = self.history.go_forward(current_loc, 1)
        self.assertEqual(loc.line, 40)

    @testlib.tag("bug81939")
    def test_jump_back(self):
        uri_stable = "file:///home/tester/stable.txt"
        uri_volatile = "file:///home/tester/volatile.txt"
        uri_current = "file:///home/tester/current.txt"
        self.history.note_loc(Location(uri_stable, 10, 0))
        self.history.note_loc(Location(uri_stable, 20, 0))
        self.history.note_loc(Location(uri_volatile, 30, 0))
        self.history.note_loc(Location(uri_stable, 40, 0))
        self.history.note_loc(Location(uri_stable, 50, 0))
        current_loc = Location(uri_current, 100, 0)
        loc = self.history.go_back(current_loc, 3)
        self.assertEqual(loc.line, 30)
        #self.history.debug_dump_recent_history(loc)
        #print "Try to get back to loc %r" % current_loc
        self.history.obsolete_uri(loc.uri, 3, True) # => #100
        #self.history.debug_dump_recent_history(None)
        # Should end up back at 100, moving back 1 takes us to 50
        loc = self.history.go_back(current_loc, 1)
        self.assertEqual(loc.line, 50)

    @testlib.tag("bug81939")
    def test_jump_forward(self):
        uri_stable = "file:///home/tester/stable.txt"
        uri_volatile = "file:///home/tester/volatile.txt"
        uri_current = "file:///home/tester/current.txt"
        self.history.note_loc(Location(uri_stable, 10, 0))
        self.history.note_loc(Location(uri_stable, 20, 0))
        self.history.note_loc(Location(uri_volatile, 30, 0))
        self.history.note_loc(Location(uri_stable, 40, 0))
        self.history.note_loc(Location(uri_stable, 50, 0))
        current_loc = Location(uri_current, 100, 0)
        loc = self.history.go_back(current_loc, 5)
        self.assertEqual(loc.line, 10)
        current_loc = loc
        loc = self.history.go_forward(current_loc, 2)
        self.assertEqual(loc.line, 30)
        #self.history.debug_dump_recent_history(loc)
        self.history.obsolete_uri(loc.uri, 2, False) # => #10
        #self.history.debug_dump_recent_history(None)
        loc = self.history.go_forward(current_loc, 1)
        self.assertEqual(loc.line, 20)

    @testlib.tag("bug81939")
    def test_move_back_into_wall(self):
        uri_stable = "file:///home/tester/stable.txt"
        uri_volatile = "file:///home/tester/volatile.txt"
        uri_current = "file:///home/tester/current.txt"
        self.history.note_loc(Location(uri_volatile, 10, 0))
        self.history.note_loc(Location(uri_volatile, 20, 0))
        self.history.note_loc(Location(uri_volatile, 30, 0))
        self.history.note_loc(Location(uri_stable, 40, 0))
        self.history.note_loc(Location(uri_stable, 50, 0))
        current_loc = Location(uri_current, 100, 0)
        loc = self.history.go_back(current_loc, 2)
        self.assertEqual(loc.line, 40)
        current_loc = loc
        loc = self.history.go_back(current_loc, 1)
        self.assertEqual(loc.line, 30)
        #self.history.debug_dump_recent_history(loc)
        self.history.obsolete_uri(loc.uri, 1, True) # => 40
        #self.history.debug_dump_recent_history(None)
        self.assertFalse(self.history.can_go_back())
        
    @testlib.tag("bug81939")
    def test_move_forward_into_wall(self):
        uri_stable = "file:///home/tester/stable.txt"
        uri_volatile = "file:///home/tester/volatile.txt"
        self.history.note_loc(Location(uri_stable, 10, 0))
        self.history.note_loc(Location(uri_stable, 20, 0))
        self.history.note_loc(Location(uri_volatile, 30, 0))
        self.history.note_loc(Location(uri_volatile, 40, 0))
        self.history.note_loc(Location(uri_volatile, 50, 0))
        current_loc = Location(uri_volatile, 100, 0)
        loc = self.history.go_back(current_loc, 4)
        self.assertEqual(loc.line, 20)
        current_loc = loc
        #self.history.debug_dump_recent_history(loc)
        loc = self.history.go_forward(current_loc, 1)
        self.assertEqual(loc.line, 30)
        #self.history.debug_dump_recent_history(loc)
        self.history.obsolete_uri(loc.uri, 1, False) # => 20
        #self.history.debug_dump_recent_history(current_loc)
        self.assertFalse(self.history.can_go_forward())
        
    @testlib.tag("bug81939")
    def test_move_forward_multi(self):
        uri_stable = "file:///home/tester/stable.txt"
        uri_volatile = "file:///home/tester/volatile.txt"
        uri_current = "file:///home/tester/current.txt"
        self.history.note_loc(Location(uri_stable, 10, 0))
        self.history.note_loc(Location(uri_stable, 20, 0))
        self.history.note_loc(Location(uri_volatile, 30, 0))
        self.history.note_loc(Location(uri_stable, 40, 0))
        self.history.note_loc(Location(uri_volatile, 50, 0))
        self.history.note_loc(Location(uri_volatile, 60, 0))
        self.history.note_loc(Location(uri_volatile, 70, 0))
        self.history.note_loc(Location(uri_volatile, 80, 0))
        self.history.note_loc(Location(uri_volatile, 90, 0))
        self.history.note_loc(Location(uri_stable, 100, 0))
        current_loc = Location(uri_current, 110, 0)
        loc = self.history.go_back(current_loc, 9)
        self.assertEqual(loc.line, 20)
        current_loc = loc
        loc = self.history.go_forward(current_loc, 5)
        self.assertEqual(loc.line, 70)
        #self.history.debug_dump_recent_history(loc)
        self.history.obsolete_uri(loc.uri, 5, False) # => #20
        #self.history.debug_dump_recent_history(current_loc)
        loc = self.history.go_forward(current_loc, 1)
        self.assertEqual(loc.line, 40)
        current_loc = loc
        loc = self.history.go_back(current_loc, 1)
        self.assertEqual(loc.line, 20)
        current_loc = loc
        loc = self.history.go_back(current_loc, 1)
        self.assertEqual(loc.line, 10)
        self.assertFalse(self.history.can_go_back())
        current_loc = loc
        loc = self.history.go_forward(current_loc, 3)
        self.assertEqual(loc.line, 100)
        current_loc = loc
        loc = self.history.go_forward(current_loc, 1)
        self.assertEqual(loc.line, 110)
        current_loc = loc
        self.assertFalse(self.history.can_go_forward())
    
    @testlib.tag("bug81939")
    def test_move_back_multi(self):
        uri_stable = "file:///home/tester/stable.txt"
        uri_volatile = "file:///home/tester/volatile.txt"
        uri_current = "file:///home/tester/current.txt"
        self.history.note_loc(Location(uri_stable, 10, 0))
        self.history.note_loc(Location(uri_stable, 20, 0))
        self.history.note_loc(Location(uri_volatile, 30, 0))
        self.history.note_loc(Location(uri_stable, 40, 0))
        self.history.note_loc(Location(uri_volatile, 50, 0))
        self.history.note_loc(Location(uri_volatile, 60, 0))
        self.history.note_loc(Location(uri_volatile, 70, 0))
        self.history.note_loc(Location(uri_volatile, 80, 0))
        self.history.note_loc(Location(uri_volatile, 90, 0))
        self.history.note_loc(Location(uri_stable, 100, 0))
        self.history.note_loc(Location(uri_stable, 110, 0))
        self.history.note_loc(Location(uri_stable, 120, 0))
        current_loc = Location(uri_current, 130, 0)
        loc = self.history.go_back(current_loc, 2)
        self.assertEqual(loc.line, 110)
        current_loc = loc
        loc = self.history.go_back(current_loc, 4)
        self.assertEqual(loc.line, 70)
        #self.history.debug_dump_recent_history(loc)
        self.history.obsolete_uri(loc.uri, 4, True) # => #110
        #self.history.debug_dump_recent_history(current_loc)
        loc = self.history.go_back(current_loc, 2)
        self.assertEqual(loc.line, 40)
        current_loc = loc
        loc = self.history.go_back(current_loc, 1)
        self.assertEqual(loc.line, 20)
        current_loc = loc
        loc = self.history.go_back(current_loc, 1)
        self.assertEqual(loc.line, 10)
        self.assertFalse(self.history.can_go_back())
        current_loc = loc
        loc = self.history.go_forward(current_loc, 5)
        self.assertEqual(loc.line, 120)
        current_loc = loc
        loc = self.history.go_forward(current_loc, 1)
        self.assertEqual(loc.line, 130)
        current_loc = loc
        self.assertFalse(self.history.can_go_forward())
    
    def test_reloading_db(self):
        """
        Build a database with locations from two URIs interleaved.
        Step one hop at a time until we find a "volatile" URI, and
        remove it.  Verify the remaining visits.
        Reload the database, verifying that
        we find all the same items.
        """
        uri_stable = "file:///home/tester/stable.txt"
        uri_volatile = "file:///home/tester/volatile.txt"
        uri_current = "file:///home/tester/current.txt"
        # Create 50 entries in the database, every 3rd is the volatile URI
        num_items_to_create = 50
        volatile_factor = 3
        uris = [uri_stable, uri_stable, uri_volatile]
        locs = [self.history.note_loc(Location(uris[i % volatile_factor],
                                               10 * (i + 1), 0))
                for i in range(num_items_to_create)]
        current_loc = Location(uri_current, num_items_to_create + 1, 0)
        locs.append(current_loc)
        loc = self.history.go_back(current_loc, 2)
        self.assertEqual(loc.uri, uri_stable)
        self.assertEqual(loc.line, 490)
        current_loc = loc
        # We want to make 1 step back into a location we'll remove.
        loc = self.history.go_back(current_loc, 1)
        self.assertEqual(loc.uri, uri_volatile)
        self.assertEqual(loc.line, 480)
        #self.history.debug_dump_recent_history(loc)
        self.history.obsolete_uri(loc.uri, 1) # => #490
        #self.history.debug_dump_recent_history(current_loc)
        v = list(self.history.recent_history(current_loc))
        # Make assertions about the culled list
        vlen = len(v)
        for i in range((vlen - 1)/2):
            self.assertEqual(v[1 + (2 * i)][1], locs[49 - 0 - (3 * i)])
            self.assertEqual(v[2 + (2 * i)][1], locs[49 - 1 - (3 * i)])
        self.assertEqual(current_loc.line, 490)

        # Now save the database, reload, and verify some facts about the
        # new database
        self.history.save()
        
        # Now reload
        self.history = History(self._db_path_)
        self.assertEqual(current_loc.line, 490)
        #self.history.debug_dump_recent_history(current_loc)
        # Recheck history
        v = list(self.history.recent_history(current_loc))
        # Make the same assertions about the culled list
        vlen = len(v)
        for i in range((vlen - 1)/2):
            self.assertEqual(v[1 + (2 * i)][1], locs[49 - 0 - (3 * i)])
            self.assertEqual(v[2 + (2 * i)][1], locs[49 - 1 - (3 * i)])

#---- mainline

if __name__ == "__main__":
    import logging
    logging.basicConfig()
    unittest.main()


