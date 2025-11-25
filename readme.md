# Components
Here's what I used, but anything that works is obviously fine!
|Component|Link|
|-|-|
|Navilink Cable|https://www.tanklessparts.com/product/navien-gxxx001659-navilink-t-extra-channel-cable|
|RS485/CAN Hat|https://www.amazon.com/dp/B07DNPFMRW|
|RJ45 Breakout|https://www.amazon.com/dp/B0CJHQNHF2|

# Wiring
You want to wire the Blue wire to A, and the Blue/White wire to B. If you're looking at your RJ45 with the latch facing down, these correspond to the 5th and 4th wires from the left respectively. You do not need to worry about using the other two wires for power.

# Protocol
Some very smart folks have already reverse engineered the majority of the protocol. Here's some useful links:
https://community.home-assistant.io/t/navien-esp32-navilink-interface/720567/20
https://github.com/htumanyan/navien/blob/main/doc/README.md

# Python Script
## Setup the environment
1. `python3 -m venv venv`
1. `source venv/bin/activate`
1. `pip install aiomqtt`
1. `pip install gpiozero`
1. `pip install lgpio`
1. `pip install pyserial`

## Running
1. `source venv/bin/python3 npe240a2.py`