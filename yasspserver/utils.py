from ssmanager import Server


ss_bind_address = '0.0.0.0'

def parse_servers_nico(profiles_json):
    """Convert JSON-array profiles sent by web server
    into a tuple instance of Server.
    """
    return (Server(host=ss_bind_address,
                   port=int(p['port']), password=p['passwd'],
                   method=p['method'], ota=p['ota']=='1',
                   udp=p['udp']=='1', fast_open=p['fastopen']=='1')
            for p in profiles_json)

def parse_servers_moyu(profiles_json):
    return (Server(host=ss_bind_address, **p) for p in profiles_json)

