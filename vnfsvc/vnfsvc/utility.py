from vnfsvc.client import client
class Utils(object):
    def __init__(self, context):
        self.neutronclient = client.NeutronClient(context)
    def _get_port_iface_map(self,interface_map):
        ip_tap_map = dict()
        port_list = self.neutronclient.get_ports()
        for iface in interface_map:
            for port in port_list:
                for fixed_ip in port['fixed_ips']:
                    if fixed_ip['ip_address'] == interface_map[iface]:
                       tap = 'tap' + port['id'][:11]
                       ip_tap_map[iface] = tap
        return ip_tap_map

