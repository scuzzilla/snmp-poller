# snmp-poller brief intro

The **snmp-poller(TM)** application can be used to handle concurrent SNMPv3 queries. 

The application is developed in [Python](https://www.python.org) (version >= 3.x) and it's based on [pysnmp's API](https://pysnmp.readthedocs.io/en/latest/index.html)
the concurrency is implemented using the [asyncio](https://docs.python.org/3.7/library/asyncio.html) framework. 

### For more details you can refer to the official [wiki page](https://www.alfanetti.org/data-pipes.html)
---
# Quick Install
```
0. git clone git@github.com:scuzzilla/snmp-poller.git
1. cd snmp-poller
2. python3 -m venv .
3. source bin/activate
4. pip install -r requirements.txt
5. ./snmp-poller -h
```
