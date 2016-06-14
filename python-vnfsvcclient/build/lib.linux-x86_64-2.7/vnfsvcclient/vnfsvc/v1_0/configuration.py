from vnfsvcclient.common import exceptions
from vnfsvcclient.vnfsvc import v1_0 as vnfsvcV20
from vnfsvcclient.openstack.common.gettextutils import _

_CONFIGURATION = 'configuration'
"""
class UpgradeConfiguration(vnfsvcV20.CreateCommand):

    resource = _CONFIGURATION
    import pdb;pdb.set_trace()

    def add_known_arguments(self, parser):
        parser.add_argument(
            '--nsd-id',
            required=True,
            help='NSD ID')
        parser.add_argument(
            '--vdu-id',
            metavar='<key>=<value>',
            action='append',
            dest='vdus',
            default=[],
            help='VDU ID\'s')

    def args2body(self, parsed_args):
        body = {
            self.resource: {
                             'nsd_id': parsed_args.nsd_id,
                             'vdus': dict()
          }
        }
        if parsed_args.vdus:
            try:
                for key_value in parsed_args.vdus:
                    kwargs = key_value.split(',')
            except ValueError:
                msg = (_('invalid argument for --kwargs %s') %
                       parsed_args.kwargs)
                raise exceptions.vnfsvcCLIError(msg)
            if kwargs:
                body[self.resource]['vdus'] = kwargs

        vnfsvcV20.update_dict(parsed_args, body[self.resource], ['tenant-id'])
        return body
"""

class UpdateConfiguration(vnfsvcV20.UpdateCommand):

    """Update a given VNF configuration."""

    resource = _CONFIGURATION

    def add_known_arguments(self, parser):
        parser.add_argument(
            '--vdu-name',
            required=True,
            help='name of the service')
        parser.add_argument(
            '--cfg-engine',
            required=True,
            help='name of cfg-engine')
        parser.add_argument(
            '--software',
            help='software to be upgraded')

    def args2body(self, parsed_args):
        body = {
            self.resource: { 'attributes':
                {
                'vdu_name': parsed_args.vdu_name,
                'cfg_engine' : parsed_args.cfg_engine,
                'software' : parsed_args.software
                }
            }
        }
        vnfsvcV20.update_dict(parsed_args, body[self.resource], ['tenant_id'])
        return body


class ListService(vnfsvcV20.ListCommand):
    """List service that belong to a given tenant."""

    resource = _CONFIGURATION


class ShowService(vnfsvcV20.ShowCommand):
    """Show information of a given VNF."""

    resource = _CONFIGURATION
