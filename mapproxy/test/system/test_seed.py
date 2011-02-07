# This file is part of the MapProxy project.
# Copyright (C) 2010 Omniscale <http://omniscale.de>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement
import os
import time
import shutil
import tempfile
from mapproxy.seed.seeder import seed
from mapproxy.seed.cleanup import cleanup
from mapproxy.seed.config import load_seed_tasks_conf

from mapproxy.test.http import mock_httpd
from mapproxy.test.image import tmp_image

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'fixture')

class SeedTestBase(object):
    def setup(self):
        self.dir = tempfile.mkdtemp()
        shutil.copy(os.path.join(FIXTURE_DIR, self.seed_conf_name), self.dir)
        shutil.copy(os.path.join(FIXTURE_DIR, self.mapproxy_conf_name), self.dir)
        self.seed_conf_file = os.path.join(self.dir, self.seed_conf_name)
        self.mapproxy_conf_file = os.path.join(self.dir, self.mapproxy_conf_name)
        
    def teardown(self):
        shutil.rmtree(self.dir)
    
    def make_tile(self, coord=(0, 0, 0), timestamp=None):
        """
        Create file for tile at `coord` with given timestamp.
        """
        tile_dir = os.path.join(self.dir, 'cache/one_EPSG4326/%02d/000/000/%03d/000/000/' %
                                (coord[2], coord[0]))
        os.makedirs(tile_dir)
        tile = os.path.join(tile_dir + '%03d.png' % coord[1])
        open(tile, 'w').write('')
        if timestamp:
            os.utime(tile, (timestamp, timestamp))
        return tile
    
    def tile_exists(self, coord):
        tile_dir = os.path.join(self.dir, 'cache/one_EPSG4326/%02d/000/000/%03d/000/000/' %
                                (coord[2], coord[0]))
        tile = os.path.join(tile_dir + '%03d.png' % coord[1])
        return os.path.exists(tile)

    def test_seed_dry_run(self):
        tasks, cleanup_tasks = load_seed_tasks_conf(self.seed_conf_file, self.mapproxy_conf_file)
        seed(tasks, verbose=False, dry_run=True)
        cleanup(cleanup_tasks, verbose=False, dry_run=True)
    
    def test_seed(self):
        with tmp_image((256, 256), format='png') as img:
            img_data = img.read()
            expected_req = ({'path': r'/service?LAYERS=foo&SERVICE=WMS&FORMAT=image%2Fpng'
                                  '&REQUEST=GetMap&VERSION=1.1.1&bbox=-180.0,-90.0,180.0,90.0'
                                  '&width=256&height=128&srs=EPSG:4326'},
                            {'body': img_data, 'headers': {'content-type': 'image/png'}})
            with mock_httpd(('localhost', 42423), [expected_req]):
                tasks, cleanup_tasks  = load_seed_tasks_conf(self.seed_conf_file, self.mapproxy_conf_file)
                seed(tasks, verbose=False, dry_run=False)
                cleanup(cleanup_tasks, verbose=False, dry_run=False)

    def test_reseed_uptodate(self):
        # tile already there.
        self.make_tile((0, 0, 0))
        tasks, cleanup_tasks  = load_seed_tasks_conf(self.seed_conf_file, self.mapproxy_conf_file)
        seed(tasks, verbose=False, dry_run=False)
        cleanup(cleanup_tasks, verbose=False, dry_run=False)

class TestSeedOldConfiguration(SeedTestBase):
    seed_conf_name = 'seed_old.yaml'
    mapproxy_conf_name = 'seed_mapproxy.yaml'

    def test_reseed_remove_before(self):
        # tile already there but too old
        t000 = self.make_tile((0, 0, 0), timestamp=time.time() - (60*60*25))
        # old tile outside the seed view (should be removed)
        t001 = self.make_tile((0, 0, 1), timestamp=time.time() - (60*60*25))
        assert os.path.exists(t000)
        assert os.path.exists(t001)
        with tmp_image((256, 256), format='png') as img:
            img_data = img.read()
            expected_req = ({'path': r'/service?LAYERS=foo&SERVICE=WMS&FORMAT=image%2Fpng'
                                  '&REQUEST=GetMap&VERSION=1.1.1&bbox=-180.0,-90.0,180.0,90.0'
                                  '&width=256&height=128&srs=EPSG:4326'},
                            {'body': img_data, 'headers': {'content-type': 'image/png'}})
            with mock_httpd(('localhost', 42423), [expected_req]):
                tasks, cleanup_tasks = load_seed_tasks_conf(self.seed_conf_file, self.mapproxy_conf_file)
                seed(tasks, verbose=True, dry_run=False)
                cleanup(cleanup_tasks, verbose=False, dry_run=False)
        
        assert os.path.exists(t000)
        assert os.path.getmtime(t000) - 5 < time.time() < os.path.getmtime(t000) + 5
        assert not os.path.exists(t001)

class TestSeed(SeedTestBase):
    seed_conf_name = 'seed.yaml'
    mapproxy_conf_name = 'seed_mapproxy.yaml'
    
    def test_cleanup_levels(self):
        tasks, cleanup_tasks  = load_seed_tasks_conf(self.seed_conf_file, self.mapproxy_conf_file)
        cleanup_tasks = [t for t in cleanup_tasks if t.md['name'] == 'cleanup']
        
        self.make_tile((0, 0, 0))
        self.make_tile((0, 0, 1))
        self.make_tile((0, 0, 2))
        self.make_tile((0, 0, 3))
        
        cleanup(cleanup_tasks, verbose=False, dry_run=False)
        assert not self.tile_exists((0, 0, 0))
        assert not self.tile_exists((0, 0, 1))
        assert self.tile_exists((0, 0, 2))
        assert not self.tile_exists((0, 0, 3))

    def test_cleanup_coverage(self):
        tasks, cleanup_tasks  = load_seed_tasks_conf(self.seed_conf_file, self.mapproxy_conf_file)
        cleanup_tasks = [t for t in cleanup_tasks if t.md['name'] == 'with_coverage']
        
        self.make_tile((0, 0, 0))
        self.make_tile((1, 0, 1))
        self.make_tile((2, 0, 2))
        self.make_tile((2, 0, 3))
        self.make_tile((4, 0, 3))
        
        cleanup(cleanup_tasks, verbose=False, dry_run=False)
        assert not self.tile_exists((0, 0, 0))
        assert not self.tile_exists((1, 0, 1))
        assert self.tile_exists((2, 0, 2))
        assert not self.tile_exists((2, 0, 3))
        assert self.tile_exists((4, 0, 3))

