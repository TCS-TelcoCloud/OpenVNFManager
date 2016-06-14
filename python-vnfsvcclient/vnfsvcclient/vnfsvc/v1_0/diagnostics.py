from vnfsvcclient.common import exceptions
from vnfsvcclient.vnfsvc import v1_0 as vnfsvcV20
from vnfsvcclient.openstack.common.gettextutils import _

_DIAGNOSTICS = 'diagnostic'

class StartDiagnostics(vnfsvcV20.CreateCommand):
    """Invokes diagnostics operation"""

    resource = _DIAGNOSTICS

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

class StopDiagnostics(vnfsvcV20.DeleteCommand):
    """stops the diagnostics."""

    resource = _DIAGNOSTICS 
