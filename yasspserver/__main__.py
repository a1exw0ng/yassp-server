#!/usr/bin/env python3
import os
import sys
import time
import logging
from os.path import isfile
from configparser import ConfigParser

from ssmanager import Manager, Server
from .yassp import YaSSP
from . import pushserver


def get_config():
    if len(sys.argv) != 2:
        print('Usage:\n\t%s <PATH-TO-CONFIG-FILE>' % sys.argv[0])
        sys.exit(1)
    path = sys.argv[1]
    if not isfile(path):
        print('Error: config file "%s" not exist.' % path)
        sys.exit(1)
    config = ConfigParser()
    config.read(path)
    return config['DEFAULT']


def main():
    conf = get_config()
    logging.basicConfig(level=conf.getint('log level'),
                        format='%(asctime)s %(levelname)-s: %(message)s')
    manager = Manager(ss_bin=conf['ss-server path'],
                      print_ss_log=conf.getboolean('ss-server print log'))

    yassp = YaSSP(conf['yassp url'], conf['yassp hostname'], conf['yassp psk'], manager)

    try:
        yassp.start()
        if conf.getboolean('push server enable'):
            pushserver.run(manager, conf['push token'],
                           host=conf['push bind address'],
                           port=conf.getint('push bind port'))
        else:
            yassp._listen_thread.join()
    except KeyboardInterrupt:
        logging.info('Stopped by ^C.')
    finally:
        manager.stop()


if __name__ == '__main__':
    main()

