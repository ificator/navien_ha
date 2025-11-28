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
Some very smart folks have already reverse engineered the majority of the protocol. Here's some useful links from which I derived my own parsing:  
1. https://community.home-assistant.io/t/navien-esp32-navilink-interface/720567/20
2. https://github.com/htumanyan/navien
3. https://github.com/dacarson/NavienManager
4. https://github.com/evanjarrett/ESPHome-Navien

## Header
|Byte Start|Length|Description|Values|
|-|-|-|-|
|0|2|packet start marker|always `0x05F7`|
|2|1|direction|`0x0F` = control<br>`0x50` = status|
|3|1|type|`0x0F` = gas<br>`0x50` = water|
|4|1|unknown|always `0x90`|
|5|1|length||

## Gas
*NOTE: multi-byte numbers are in little-endian*
|Byte Start|Length|Description|Values|
|-|-|-|-|
|6|1|status type|always `0x45`|
|8|1|unknown|always `0x0B`|
|9|1|unknown|always `0x01`|
|10|2|controller version|not convinced... byte 10 is the F/W version (`0x0C` = 1.2) but what is byte 11|
|12|2|panel version|not convinced... byte 12 is the F/W version (`0x19` = 2.5) but what is byte 13|
|14|1|set temperature|C value in increments of 0.5|
|15|1|water outlet temperature|C value in increments of 0.5|
|16|1|water inlet temperature|C value in increments of 0.5|
|17|1|unknown|always `0x00`|
|18|1|unknown|always `0x00`|
|19|2|target burner power|kcal|
|21|1|unknown|always `0x01`|
|22|2|current burner power|kcal|
|24|2|total gas usage|m3 in increments of 0.1|
|26|1|unknown|always `0x00`|
|27|1|unknown|always `0x00`|
|28|2|elapsed time since install|days|
|30|2|usage counter|increments of 10|
|32|4|unknown|incrementing - possibly a 4-byte number?|
|36|2|operation time|hours|
|38|1|unknown|always `0x00`|
|39|1|unknown|always `0x00`|
|40|1|unknown|always `0x00`|
|41|1|unknown|always `0x00`|
|42|1|unknown|always `0xAA`|
|43|1|unknown|always `0x48`|
|44|1|unknown|always `0x00`|
|45|1|unknown|always `0x00`|
|46|1|recirculation enabled|`0x00` = no<br>`0x01` = yes|
|47|1|unknown|always `0x00`|
|48|1|CRC||

## Water
*NOTE: multi-byte numbers are in little-endian*
|Byte Start|Length|Description|Values|
|-|-|-|-|
|6|1|status type|always `0x42`|
|7|1|unknown|always `0x00`|
|8|1|flow detected|`0x08` = recirculating<br>`0x20` = demand|
|9|1|system power|`0x05` = on<br>`0x25` = recirculation active|
|10|1|system stage|`0x1-` = idle<br>&nbsp;&nbsp;`0x14` = stand-by<br>`0x2-` = start up<br>&nbsp;&nbsp;`0x20` = ?<br>&nbsp;&nbsp;`0x29` = ?<br>&nbsp;&nbsp;`0x2B` = ?<br>&nbsp;&nbsp;`0x2C` = ?<br>&nbsp;&nbsp;`0x2D` = ?<br>`0x3-` = active<br>&nbsp;&nbsp;`0x33` = in use<br>&nbsp;&nbsp;`0x3C` = turning burner off (2s)<br>`0x4-` = shut down<br>&nbsp;&nbsp;`0x46` = post-purge 1/2 (15s)<br>&nbsp;&nbsp;`0x47` = post-purge 2/2 (15s)<br>&nbsp;&nbsp;`0x49` = dhw-wait (150s)|
|11|1|set temperature|C value in increments of 0.5|
|12|1|heat exchanger outlet temperature|C value in increments of 0.5|
|13|1|heat exchanger inlet temperature|C value in increments of 0.5|
|14|1|unknown|always `0x00`|
|15|1|unknown|always `0x00`|
|16|1|unknown|always `0x00`|
|17|1|capacity|percentage|
|18|1|flow rate|lpm in increments of 0.1|
|19|1|unknown|always `0x00`|
|20|1|unknown|always `0xA0`|
|21|1|unknown|always `0xBE`|
|22|1|unknown|always `0x00`|
|23|1|unknown|always `0x20`|
|24|1|system configuration|`0x01` = internal recirculation<br>`0x02` = external recirculation<br>`0x08` = metric|
|25|1|unknown|always `0x00`|
|26|1|unknown|always `0x00`|
|27|1|system active|`0x00` = no<br>`0x01` = yes|
|28|2|unknown counter|incrementing|
|29|1|unknown|always `0x00`|
|30|1|unknown|always `0x01`|
|31|1|unknown|always `0x00`|
|32|1|unknown|always `0x00`|
|33|1|unknown|always `0x02` (even when recirculation is off)|
|34|1|unknown|always `0x00`|
|35|1|unknown|always `0x00`|
|36|1|unknown|always `0x00`|
|37|1|unknown|always `0x00`|
|38|1|unknown|always `0x00`|
|39|1|unknown|always `0x00`|
|40|1|CRC||

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