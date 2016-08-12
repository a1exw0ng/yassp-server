import time
import json
import logging
import requests
from requests.exceptions import RequestException, ConnectionError
from threading import Thread
from collections import defaultdict
from urllib.parse import urljoin

from .utils import parse_servers_nico, parse_servers_moyu


TRAFFIC_CHECK_PERIOD = 30

class YaSSP():
    traffic_sync_threshold = 100 * 1024 * 1024  # 100 MiB
    traffic_sync_timeout = 60 * 30  # 30 mins

    def __init__(self, yassp_type, url_prefix, hostname, psk, manager):
        self._running = False
        self._synced_traffic = defaultdict(lambda: 0)
        self._earliest_unsynced_time = {}

        if yassp_type not in ('nico', 'moyu'):
            raise KeyError('YaSSP type "%s" is not "nico" or "moyu".' \
                           % yassp_type)
        self._type = yassp_type
        self._url_prefix = url_prefix
        self._hostname = hostname
        self._psk = psk
        self._manager = manager

    def _request(self, func, path, **kwargs):
        params = kwargs.pop('params', {})
        if self._type == 'nico':
            params['token'] = self._psk
            auth = None
        else:
            auth=(self._hostname, self._psk)
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 10
        req = func(urljoin(self._url_prefix, path),
                   params=params, auth=auth,
                   **kwargs)
        if req.status_code == 403:
            raise AuthenticationError()
        elif req.status_code == 200:
            return req.json()
        elif req.status_code == 204:
            return
        else:
            raise UnexpectedResponseError()

    def _get(self, *args, **kwargs):
        return self._request(requests.get, *args, **kwargs)

    def _post(self, *args, **kwargs):
        return self._request(requests.post, *args, **kwargs)

    def start(self):
        self._listen_thread = Thread(target=self._listen_profile_changes, daemon=True)
        self._traffic_thread = Thread(target=self._traffic_timer, daemon=True)
        self._running = True
        self.update_profiles()
        self._listen_thread.start()
        self._traffic_thread.start()

    def stop(self):
        self._running = False
        self.update_traffic(force_all=True)

    def update_profiles(self):
        try:
            if self._type == 'nico':
                profiles = self._get('getport.php', params=dict(act='list'))
                servers = parse_servers_nico(profiles)
                self._manager.update(parse_servers_nico(profiles))
            elif self._type == 'moyu':
                profiles = self._get('services/')
                servers = parse_servers_moyu(profiles)
                self._manager.update(parse_servers_moyu(profiles))
            else:
                raise NotImplementedError()
            logging.debug('Syncing %s profiles (pull)...' % len(profiles))
        except (RequestException, AuthenticationError, UnexpectedResponseError,
                ConnectionError, ValueError, KeyError) as e:
            logging.warning('Error on update profiles: %s' % e)
            return

    def update_traffic(self, force_all=False):
        stat = self._manager.stat()
        to_upload = {}
        for port, traffic in stat.items():
            increment = traffic - self._synced_traffic[port]
            if increment == 0:
                continue
            if increment < 0:
                self._synced_traffic[port] = 0
                increment = traffic

            if port not in self._earliest_unsynced_time:
                self._earliest_unsynced_time[port] = time.time()
            if time.time() - self._earliest_unsynced_time[port] > self.traffic_sync_timeout \
               or increment >= self.traffic_sync_threshold \
               or force_all:
                to_upload[port] = increment

        if to_upload:
            logging.debug('Uploading traffic (%d)...' % len(to_upload))
            logging.debug(to_upload)
            try:
                if self._type == 'nico':
                    to_post = {'update': list(dict(port=p, transfer=t) for p, t in to_upload.items())}
                    resp = self._post('getport.php', params=dict(act='updates'), data=json.dumps(to_post))
                    if resp.get('code') != 200:
                        logging.debug(resp)
                        raise UnexpectedResponseError('Code returned by server %s != 200.' % resp.get('code'))
                elif self.type == 'moyu':
                    self._post('traffics/', data=json.dumps(to_upload))
                else:
                    raise NotImplementedError()
            except (RequestException, AuthenticationError, UnexpectedResponseError, ConnectionError) as e:
                logging.warning('Error on upload traffic: %s' % e)
            else:
                for port, __ in to_upload.items():
                    self._synced_traffic[port] = stat[port]
                    if port in self._earliest_unsynced_time:
                        del self._earliest_unsynced_time[port]

    def _listen_profile_changes(self):
        # Currently, we just fetch all profiles every 1 minutes.
        timeout = 60 * 1
        time.sleep(timeout)
        while self._running:
            self.update_profiles()
            time.sleep(timeout)

    def _traffic_timer(self):
        while self._running:
            time.sleep(min(TRAFFIC_CHECK_PERIOD, self.traffic_sync_timeout))
            self.update_traffic()


class AuthenticationError(Exception):
    pass

class UnexpectedResponseError(Exception):
    pass

