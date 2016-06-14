import uuid

class ParserUtils(object):

    def __init__(self):
         super(ParserUtils, self).__init__()
    #    self.new_nsd = nsd_new

    def lifecycle_event(self, data, new_nsd):
        new_nsd['postconfigure']['lifecycle_event'] = data


    def endpoints(self, data, new_nsd):
        new_nsd['postconfigure']['endpoints'] = data

    def assurance_params(self, data, new_nsd):
        new_nsd['postconfigure']['assurance_params'] = data

    def cfg_engine(self, data, new_nsd):
        new_nsd['preconfigure']['cfg_engine'] = data

    def member_vnfs(self, data, new_nsd, nsd):
        new_nsd['vnfds'] = dict()
        new_nsd['vdus'] = dict()
        for vdu in data:
            if vdu['name'] not in new_nsd['vnfds'].keys():
                new_nsd['vnfds'][vdu['name']] = list()
            new_nsd['vnfds'][vdu['name']].append(vdu['member-vdu-id'])
            vdu_name = vdu['name']+':'+vdu['member-vdu-id']
            new_nsd['vdus'][vdu_name] =dict()
            new_nsd['vdus'][vdu_name]['id'] = str(uuid.uuid4())
            if 'dependency' in vdu.keys():
                if isinstance(vdu['dependency'], list):
                    new_nsd['vdus'][vdu_name]['dependency'] = vdu['dependency']
                else:
                    new_nsd['vdus'][vdu_name]['dependency'] = [vdu['dependency']]

    def member_vlds(self, data, new_nsd, nsd):
        #self.member_vnfs(self, nsd.nsd['member_vnfs'], new_nsd, nsd)
        new_nsd['networks'] = dict()
        for network in data:
            temp_dict = dict()
            temp_dict['id'] = nsd.networks[network]
            temp_dict['property'] = data[network]['property']
            #@TODO:Assuming one subnet for one network --- need to modify
            temp_dict['subnet_id'] = nsd.subnets[network]
            if 'Router' in data[network].keys():
                if not 'router' in  nsd.new_nsd['preconfigure'].keys():
                    new_nsd['preconfigure']['router'] = dict()
                temp_dict['Router'] = nsd.router
                new_nsd['preconfigure']['router'][network] = {
                    'name': nsd.router,
                    'network': nsd.networks[network],
                    'subnet_id': nsd.subnets[network],
                    'if_name':  data[network]['Router']}
            new_nsd['networks'][network] = temp_dict
            self.add_networks(data[network]['member-vnfs'],nsd.networks[network], nsd.subnets[network], new_nsd)


    def add_networks(self, data, network_id, subnet_id, new_nsd):
        if data is None:
            return
        for key in data:
            interfaces = data[key]['connection-point']
            if type(interfaces) == type([]):
                for interface in interfaces:
                    if 'networks' not in nsd.new_nsd['vdus'][key].keys():
                        new_nsd['vdus'][key]['networks'] = dict()
                    new_nsd['vdus'][key]['networks'][interface] = {'net-id': network_id, 'subnet-id':subnet_id}
            else:
                if 'networks' not in new_nsd['vdus'][key].keys():
                    new_nsd['vdus'][key]['networks'] = dict()
                new_nsd['vdus'][key]['networks'][interfaces] = {'net-id': network_id, 'subnet-id':subnet_id}

    def forwarding_graphs(self, data, new_nsd):
        new_nsd['postconfigure']['forwarding_graphs'] = data

    def get_forwarding_graph(self, nsd_template):
        return nsd_template['postconfigure']['forwarding_graphs']['WebAccess']['network-forwarding-path']
