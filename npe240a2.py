from aiomqtt import Client, MqttError
from gpiozero import OutputDevice
from typing import Self
import asyncio
import serial
import time

# Debug mode
DEBUG_MODE = False

# MQTT
MQTT_BROKER = "<broker>"
MQTT_USER = "<user>"
MQTT_PASSWORD = "<password>"
MQTT_TOPIC_GAS_CURRENT_USAGE = "npe240a2/gas/current"
MQTT_TOPIC_GAS_TOTAL_USAGE = "npe240a2/gas/total"
MQTT_TOPIC_WATER_CAPACITY = "npe240a2/water/capacity"
MQTT_TOPIC_WATER_OUTLET_TEMP = "npe240a2/water/outlet_temp"
MQTT_TOPIC_WATER_FLOW_RATE = "npe240a2/water/flow_rate"

#region Helpers
class Helpers:
    @staticmethod
    def calculate_crc(buffer: bytes):
        """
        Calculate a checksum/CRC value for the given buffer.
        
        Args:
            buffer: bytes or bytearray to calculate checksum for
            seed: 16-bit seed value (0-65535)
        
        Returns:
            byte: checksum value (0-255)
        """
        length = len(buffer)
        
        if length < 2:
            result = 0x00
        else:
            result = 0xff
            
            for i in range(length):
                result = result << 1
                
                if result > 0xff:
                    result = (result & 0xff) ^ 0x4b
                
                # XOR with only the lower byte of result
                result = (result & 0xff) ^ buffer[i]
        
        return result & 0xff

    @staticmethod
    def combine_bytes(data: bytes, index: int, length: int) -> int:
        """Combines the provided bytes into an integer"""
        return int.from_bytes(Helpers.slice_bytes(data, index, length), byteorder='little')

    @staticmethod
    def convert_c_f(celsius: float) -> float:
        """Convert Celsius to Fahrenheit"""
        return round(celsius * 9/5 + 32, 1)

    @staticmethod
    def convert_kcal_btu(kcal: int) -> int:
        """Convert kcal to BTU"""
        return round(kcal * 3.965667, 0)

    @staticmethod
    def convert_lpm_gpm(lpm: float) -> float:
        """Convert LPM to GPM"""
        return round(lpm * 0.264172, 1)

    @staticmethod
    def convert_m3_ccf(m3: float) -> float:
        """Convert m3 to ccf"""
        return round(m3 * 0.353147, 1)

    @staticmethod
    def format_hex(data: bytes) -> str:
        """Format bytes as hex string"""
        return ' '.join(f'{b:02x}' for b in data)

    @staticmethod
    def slice_bytes(data: bytes, index: int, length: int) -> bytes:
        """Slices bytes using an index and length"""
        return data[index:index+length]
#endregion Helpers

#region Packets
class Header:
    MARKER_LO = 0xF7
    MARKER_HI = 0x05

    GAS_ID = 0x0f
    WATER_ID = 0x50

    def __init__(self: Self, data: bytes):
        self.marker = Helpers.combine_bytes(data, 0, 2)
        self.direction = data[2]
        self.type = data[3]
        self.unknown_4 = data[4]
        self.length = data[5]

class Packet:
    def __init__(self: Self, data: bytes):
        self.data = data
        self.header = Header(data)
        self.crc = data[-1]

class GasPacket:
    def __init__(self: Self, packet: Packet):
        self._packet = packet

    @property
    def command_type(self: Self) -> int:
        """The command type, always 0x45 for gas"""
        return self._packet.data[6]
    
    @property
    def unknown_7_9(self: Self) -> bytes:
        """Bytes [7,8,9] are unknown"""
        return self._packet.data[7:10]
    
    @property
    def controller_version(self: Self) -> int:
        """The controller version"""
        return Helpers.combine_bytes(self._packet.data, 10, 2)

    @property
    def panel_version(self: Self) -> int:
        """The panel version"""
        return Helpers.combine_bytes(self._packet.data, 12, 2)

    @property
    def water_set_temp_c(self: Self) -> float:
        """The set temperature for the water"""
        return self._packet.data[14] * 0.5

    @property
    def water_set_temp_f(self: Self) -> float:
        """The set temperature for the water"""
        return Helpers.convert_c_f(self.water_set_temp_c)
    
    @property
    def water_outlet_temp_c(self: Self) -> float:
        """The outlet temperature of the water"""
        return self._packet.data[15] * 0.5

    @property
    def water_outlet_temp_f(self: Self) -> float:
        """The outlet temperature of the water"""
        return Helpers.convert_c_f(self.water_outlet_temp_c)
    
    @property
    def water_inlet_temp_c(self: Self) -> float:
        """The inlet temperature of the water"""
        return self._packet.data[16] * 0.5
    
    @property
    def water_inlet_temp_f(self: Self) -> float:
        """The inlet temperature of the water"""
        return Helpers.convert_c_f(self.water_inlet_temp_c)

    @property
    def unknown_17_18(self: Self) -> bytes:
        """Bytes [17,18] are unknown"""
        return self._packet.data[17:19]

    @property
    def gas_set_usage_kcal(self: Self) -> int:
        """The set gas usage"""
        return Helpers.combine_bytes(self._packet.data, 19, 2)

    @property
    def gas_set_usage_btu(self: Self) -> int:
        """The set gas usage"""
        return Helpers.convert_kcal_btu(self.gas_set_usage_kcal)

    @property
    def gas_current_usage_kcal(self: Self) -> int:
        """The current gas usage"""
        return Helpers.combine_bytes(self._packet.data, 22, 2)

    @property
    def gas_current_usage_btu(self: Self) -> int:
        """The current gas usage"""
        return Helpers.convert_kcal_btu(self.gas_current_usage_kcal)

    @property
    def gas_total_usage_m3(self: Self) -> float:
        """The total gas usage"""
        return Helpers.combine_bytes(self._packet.data, 24, 2) / 10.0

    @property
    def gas_total_usage_ccf(self: Self) -> float:
        """The total gas usage, in ccf"""
        return Helpers.convert_m3_ccf(self.gas_total_usage_m3)

    @property
    def unknown_26_29(self: Self) -> bytes:
        """Bytes [26,27,28,29] are unknown"""
        return self._packet.data[26:30]

    @property
    def usage_counter(self: Self) -> int:
        """Domestic usage counter in 10 usage increments"""
        return Helpers.combine_bytes(self._packet.data, 30, 2)

    @property
    def unknown_32_35(self: Self) -> bytes:
        """Bytes [32,33,34,35] are unknown"""
        return self._packet.data[32:36]
    
    @property
    def total_run_time_h(self: Self) -> int:
        """The total time the system has been active"""
        return Helpers.combine_bytes(self._packet.data, 36, 2)

    @staticmethod
    def decode(packet: Packet) -> Self:
        if packet.header.length == 42:
            return GasPacket(packet)
        return None

class WaterPacket:
    FLOW_STATE_OFF = 0x00
    FLOW_STATE_RECIRCULATING = 0x08
    FLOW_STATE_ACTIVE = 0x20

    def __init__(self: Self, packet: Packet):
        self._packet = packet

    @property
    def command_type(self: Self) -> int:
        """The command type, always 0x42 for gas"""
        return self._packet.data[6]
    
    @property
    def unknown_7(self: Self) -> bytes:
        """Bytes [7] are unknown"""
        return Helpers.slice_bytes(self._packet.data, 7, 1)

    @property
    def flow_state(self: Self) -> int:
        """The flow state of the system"""
        return self._packet.data[8]

    @property
    def system_power(self: Self) -> int:
        """ System power information """
        return self._packet.data[9]
    
    @property
    def unknown_10(self: Self) -> bytes:
        """Bytes [10] are unknown"""
        return Helpers.slice_bytes(self._packet.data, 10, 1)

    @property
    def water_set_temp_c(self: Self) -> float:
        """The set temperature for the water"""
        return self._packet.data[11] * 0.5

    @property
    def water_set_temp_f(self: Self) -> float:
        """The set temperature for the water"""
        return Helpers.convert_c_f(self.water_set_temp_c)

    @property
    def heatexchanger_outlet_temp_c(self: Self) -> float:
        """The outlet temperature of the heat exchanger"""
        return self._packet.data[12] * 0.5

    @property
    def heatexchanger_outlet_temp_f(self: Self) -> float:
        """The outlet temperature of the heat exchanger"""
        return Helpers.convert_c_f(self.heatexchanger_outlet_temp_c)

    @property
    def heatexchanger_inlet_temp_c(self: Self) -> float:
        """The inlet temperature of the heat exchanger"""
        return self._packet.data[13] * 0.5

    @property
    def heatexchanger_inlet_temp_f(self: Self) -> float:
        """The inlet temperature of the heat exchanger"""
        return Helpers.convert_c_f(self.heatexchanger_inlet_temp_c)

    @property
    def unknown_14_16(self: Self) -> bytes:
        """Bytes [14,15,16] are unknown"""
        return self._packet.data[14:17]

    @property
    def operating_capacity(self: Self) -> int:
        """The capacity at which the system is running"""
        return self._packet.data[17] * 0.5

    @property
    def flow_rate_lpm(self: Self) -> float:
        """The rate at which water is flowing through the system"""
        return self._packet.data[18] / 10.0

    @property
    def flow_rate_gpm(self: Self) -> float:
        """The rate at which water is flowing through the system"""
        return Helpers.convert_lpm_gpm(self.flow_rate_lpm)

    @property
    def unknown_19_23(self: Self) -> bytes:
        """Bytes [19,20,21,22,23] are unknown"""
        return self._packet.data[19:24]

    @property
    def system_status(self: Self) -> int:
        """The system status"""
        return self._packet.data[24]
    
    @property
    def system_status_metric(self: Self) -> bool:
        """Indicates whether the system displays in metric"""
        return self.system_status & 0x08
    
    @property
    def unknown_25_32(self: Self) -> bytes:
        """Bytes [25,26,27,28,29,30,31,32] are unknown"""
        return self._packet.data[25:33]

    @property
    def recirculation_enabled(self: Self) -> int:
        """Recirculation enabled?"""
        return self._packet.data[33]

    @property
    def unknown_34_39(self: Self) -> bytes:
        """Bytes [34,35,36,37,38,39] are unknown"""
        return self._packet.data[34:40]

    @staticmethod
    def decode(packet: Packet) -> Self:
        if packet.header.length == 34:
            return WaterPacket(packet)
        return None
#endregion Packets

#region Mqtt
class MqttState:
    def __init__(self: Self):
        self.gas_current_usage_btu: float = None
        self.gas_total_usage_ccf: float = None
        self.water_capacity: float = None
        self.water_outlet_temp_f: float = None
        self.water_flow_rate_gpm: float = None

        self._last_publish_time = {}
        self._publish_interval_sec = 5.0

    async def publish_changes(self: Self, client: Client, new_state: Self):
        if not DEBUG_MODE:
            await self.try_publish(client, new_state, MQTT_TOPIC_GAS_CURRENT_USAGE, "gas_current_usage_btu")
            await self.try_publish(client, new_state, MQTT_TOPIC_GAS_TOTAL_USAGE, "gas_total_usage_ccf")
            await self.try_publish(client, new_state, MQTT_TOPIC_WATER_CAPACITY, "water_capacity")
            await self.try_publish(client, new_state, MQTT_TOPIC_WATER_FLOW_RATE, "water_flow_rate_gpm")
            await self.try_publish(client, new_state, MQTT_TOPIC_WATER_OUTLET_TEMP, "water_outlet_temp_f")

    async def try_publish(self: Self, client: Client, newstate: Self, topic: str, attr_name: str):
        current_value = getattr(self, attr_name)
        new_value = getattr(newstate, attr_name)
        if new_value is not None and new_value != current_value:
            current_time = time.time()
            last_publish = self._last_publish_time.get(topic)
            if last_publish is None or current_time - last_publish >= self._publish_interval_sec:
                self._last_publish_time[topic] = current_time
                setattr(self, attr_name, new_value)
                await client.publish(topic, str(new_value), retain=True)
#endregion Mqtt

current_state = MqttState()

async def main():
    try:
        # Configure serial for reading
        EN_485 = OutputDevice(4)
        EN_485.off()
        ser = serial.Serial(
            "/dev/ttyAMA0",
            baudrate=19200,
            bytesize=serial.EIGHTBITS,
            stopbits=serial.STOPBITS_ONE,
            parity=serial.PARITY_NONE,
            timeout=1)
        
        while True:
            try:
                print(f"Connecting to MQTT broker at {MQTT_USER}@{MQTT_BROKER}...")
                async with Client(MQTT_BROKER, username=MQTT_USER, password=MQTT_PASSWORD) as client:
                    print("Connected!")
                    await main_loop(ser, client)
            except MqttError as e:
                print(f"MQTT failure, will reconnect: {e}")
    except asyncio.CancelledError:
        print("\nShutting down gracefully...")
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Unhandled error: {e}")
    finally:
        if 'ser' in locals():
            ser.close()
            print("Serial port closed.")

async def main_loop(ser, client):
    while True:
        packet = read_packet(ser)
        if packet:
            if DEBUG_MODE:
                # Dump raw packet for manual parsing
                print(f"Raw packet ({len(packet.data)} bytes): {Helpers.format_hex(packet.data)}")

            # Check packet type
            packet_type = packet.header.type
            if packet_type == Header.GAS_ID:
                gasPacket = GasPacket.decode(packet)
                if gasPacket is not None:
                    await process_gas_packet(client, gasPacket)
                elif DEBUG_MODE:
                    print(f"  -> Invalid gas packet")
            elif packet_type == Header.WATER_ID:
                waterPacket = WaterPacket.decode(packet)
                if waterPacket is not None:
                    await process_water_packet(client, waterPacket)
                elif DEBUG_MODE:
                    print(f"  -> Invalid water packet")
            elif DEBUG_MODE:
                print(f"  -> Unknown packet type: {packet_type:02x}")
            
            if DEBUG_MODE:
                # Blank line between packets
                print("")

async def process_gas_packet(client, packet: GasPacket):
    """Parse gas-related packet (Packet B)"""

    if DEBUG_MODE:
        print(f"  Time: {time.time()}")
        print(f"  Type: Gas")
        print(f"  Current Gas Usage: {packet.gas_current_usage_kcal} kcal / {packet.gas_current_usage_btu} btu")
        print(f"  Target Gas Usage: {packet.gas_set_usage_kcal} kcal / {packet.gas_set_usage_btu} btu")
        print(f"  Total Gas Usage: {packet.gas_total_usage_m3} m³ / {packet.gas_total_usage_ccf} ccf")
        print(f"  Water Set Temp: {packet.water_set_temp_c} °C / {packet.water_set_temp_f} °F")
        print(f"  Water Outlet Temp: {packet.water_outlet_temp_c} °C / {packet.water_outlet_temp_f} °F")
        print(f"  Water Inlet Temp: {packet.water_inlet_temp_c} °C / {packet.water_inlet_temp_f} °F")

    new_state = MqttState()
    new_state.gas_current_usage_btu = packet.gas_current_usage_btu
    new_state.gas_total_usage_ccf = packet.gas_total_usage_ccf
    new_state.water_outlet_temp_f = packet.water_outlet_temp_f

    await current_state.publish_changes(client, new_state)

async def process_water_packet(client, packet: WaterPacket):
    """Parse water-related packet (Packet A)"""

    if DEBUG_MODE:
        print(f"  Time: {time.time()}")
        print(f"  Type: Water")
        print(f"  System Power: {packet.system_power}")
        print(f"  System Status: 0x{packet.system_status:02x}")
        print(f"  Set Temperature: {packet.water_set_temp_c} °C / {packet.water_set_temp_f} °F")
        print(f"  Heat Exchanger Outlet Temperature: {packet.heatexchanger_outlet_temp_c} °C / {packet.heatexchanger_outlet_temp_f} °F")
        print(f"  Heat Exchanger Inlet Temperature: {packet.heatexchanger_inlet_temp_c} °C / {packet.heatexchanger_inlet_temp_f} °F")
        print(f"  Flow Capacity: {packet.operating_capacity}%")
        print(f"  Flow Rate: {packet.flow_rate_lpm} lpm / {packet.flow_rate_gpm} gpm")

    new_state = MqttState()
    new_state.water_capacity = packet.operating_capacity
    new_state.water_flow_rate_gpm = packet.flow_rate_gpm

    await current_state.publish_changes(client, new_state)

def read_packet(ser) -> Packet:
    """Read a complete packet from serial"""
    # Look for packet header
    while True:
        byte = ser.read(1)
        if not byte:
            return None
        
        if byte[0] == Header.MARKER_LO:
            # Check second header byte
            byte2 = ser.read(1)
            if not byte2:
                return None
            
            if byte2[0] == Header.MARKER_HI:
                # Read packet ID (3 bytes) and length (1 byte)
                header_rest = ser.read(4)
                if len(header_rest) < 4:
                    return None
                
                data_length = header_rest[3]
                
                # Read data + checksum
                remaining = ser.read(data_length + 1)
                if len(remaining) < data_length + 1:
                    return None
                
                # Reconstruct full packet
                packet = Packet(bytes([Header.MARKER_LO, Header.MARKER_HI]) + header_rest + remaining)

                # Make sure it's valid
                crc_actual = Helpers.calculate_crc(packet.data[:-1])
                crc_expected = packet.crc

                if crc_actual == crc_expected:
                    return packet
                elif DEBUG_MODE:
                    print(f"CRC MISMATCH!! ({crc_expected} != {crc_actual})")

if __name__ == "__main__":
    asyncio.run(main())