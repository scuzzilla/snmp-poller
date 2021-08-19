'''
### pysnmp_init_class
#
Author:           Salvatore Cuzzilla
em@il:            salvatore@cuzzilla.org
Starting date:    21-04-2021
Last change date: 19-08-2021
Release date:     TBD
'''


from pysnmp.hlapi import SnmpEngine
from pysnmp.hlapi import UsmUserData
from pysnmp.hlapi.asyncio import UdpTransportTarget
from pysnmp.hlapi import ContextData
from pysnmp.hlapi import ObjectIdentity
# from pysnmp.smi import rfc1902
from pysnmp.hlapi import ObjectType
from pysnmp.hlapi.auth import (usmHMACMD5AuthProtocol,
                               usmAesCfb128Protocol,
                               )


class PySnmpInit(object):
    '''
    init all the different components of pysnmp
    '''
    host = None
    localaddr = None
    oid = None

    def __init__(self, user_name, auth_key, priv_key) -> None:
        self.user_name = user_name
        self.auth_key = auth_key
        self.priv_key = priv_key
        self.__snmp_engine = self.init_snmp_engine()
        self.__usm_user_data = self.init_usm_user_data()
        self.__udp_transport_target = self.init_udp_transport_target(
                                       self.host,
                                       self.localaddr)
        self.__context_data = self.init_context_data()
        self.__object_type = self.init_object_type(self.oid)

    def init_snmp_engine(self):
        self.snmp_engine = SnmpEngine()
        return self.snmp_engine

    def init_usm_user_data(self):
        self.usm_user_data = UsmUserData(userName=self.user_name,
                                         authKey=self.auth_key,
                                         privKey=self.priv_key,
                                         authProtocol=usmHMACMD5AuthProtocol,
                                         privProtocol=usmAesCfb128Protocol)
        return self.usm_user_data

    def init_udp_transport_target(self, host, localaddr):
        self.udp_transport_target = \
             UdpTransportTarget((host, 161),
                                timeout=3,
                                retries=3).setLocalAddress((localaddr, 0))
        return self.udp_transport_target

    def init_context_data(self):
        self.context_data = ContextData()
        return self.context_data

    def init_object_type(self, oid):
        self.object_type = ObjectType(ObjectIdentity(oid))

        return self.object_type
