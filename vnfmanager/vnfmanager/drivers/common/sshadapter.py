import json
import subprocess
import paramiko
import logging.config
import time
logger = logging.getLogger(__name__)

class SSHClient(object):
  
    def __init__(self,host,username,password):
        self.host=host
        self.username=username
        self.password=password

    def exec_command(self,command,client,**kwargs):
        try:
            if client:
                stdin,stdout,stderr= client.exec_command(command)
                output = stdout.read()
                logger.debug(output)
                err = stderr.read()
                logger.debug(err)
                if len(err) > 0:
                    logger.debug(err)
                else:
                    return (output,err)
            else:
                process = subprocess.Popen(command.split(),
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  **kwargs)
                output ,err = process.communicate()
                if err:
                    logger.debug(err)
                else:
                    return (output, err)
        except:
            logger.warn("unable to execute the command")
            pass

    def get_ssh_conn(self,host,username,password):
    
        retry = 50
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(self.host,22,self.username,self.password)
            return client
        except paramiko.ssh_exception.AuthenticationException:
            logger.error("Invalid credentials")
        except paramiko.SSHException:
            logger.error("unable to establish the connection")
        except:
            logger.debug("Failed to establish SSH connection")
            while( retry > 0):
                try:
                    client=paramiko.SSHClient()
                    client.set_missing_host_key_policy(
                    paramiko.AutoAddPolicy())
                    client.connect(self.host,22,self.username,self.password)
                    if isinstance(client,paramiko.SSHClient):
                        retry=retry - 1
                        break
                    else:
                        time.sleep(3)
                except:
                    time.sleep(3)
                    retry = retry -1
                    logger.debug("unable to establish connection, Retrying to establish.")
            if isinstance(client,paramiko.SSHClient):
                return client
            else:
                logger.warn("Failed to establish connection")     
