'''pysnmp initialization — session components and per-request factories.'''


from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    UsmUserData,
    UdpTransportTarget,
    ContextData,
    ObjectIdentity,
    ObjectType,
    usmHMACMD5AuthProtocol,
    usmAesCfb128Protocol,
)


class PySnmpInit:
    '''
    Initializes and holds the session-level pysnmp components
    (engine, credentials, context) that are shared across all
    SNMP requests.

    Per-request objects (transport targets, object types) are
    created via factory methods that return new instances without
    storing state.
    '''

    def __init__(self, user_name, auth_key, priv_key):
        self.snmp_engine = SnmpEngine()

        self.usm_user_data = UsmUserData(
            user_name, auth_key, priv_key,
            authProtocol=usmHMACMD5AuthProtocol,
            privProtocol=usmAesCfb128Protocol,
        )

        self.context_data = ContextData()

    async def init_udp_transport_target(
        self, host, localaddr, port=161, timeout=3, retries=3,
    ):
        '''Create a new UDP transport target for a specific host.'''
        transport = await UdpTransportTarget.create(
            (host, port), timeout=timeout, retries=retries,
        )
        transport.set_local_address((localaddr, 0))
        return transport

    def init_object_type(self, oid):
        '''Create a new ObjectType for a specific OID.'''
        return ObjectType(ObjectIdentity(oid))
