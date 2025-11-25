from aiomqtt import Client, MqttError
from gpiozero import OutputDevice
import asyncio
import serial

# Debug mode
DEBUG_OFF = 0
DEBUG_PUBLISH = 1
DEBUG_ALL = 2
DEBUG_MODE = DEBUG_ALL

# Packet constants
HEADER_BYTE_0 = 0xf7
HEADER_BYTE_1 = 0x05

# Packet IDs
WATER_PACKET_ID = [0x50, 0x50, 0x90]
GAS_PACKET_ID = [0x50, 0x0f, 0x90]

# MQTT
MQTT_BROKER = "<broker>"
MQTT_USER = "<user>"
MQTT_PASSWORD = "<password>"
MQTT_TOPIC_GAS_CURRENT_USAGE = "npe240a2/gas/current"
MQTT_TOPIC_GAS_TOTAL_USAGE = "npe240a2/gas/total"
MQTT_TOPIC_WATER_OUTLET_TEMP = "npe240a2/water/outlet_temp"
MQTT_TOPIC_WATER_FLOW_RATE = "npe240a2/water/flow_rate"

class HomeAssistantState:
    def __init__(self):
        self.gas_current_usage_kcal = -1.0
        self.gas_total_usage_ccf = -1.0
        self.water_outlet_temp = -1.0
        self.water_flow_rate = -1.0

homeAssistantState = HomeAssistantState()

def convert_c_f(celsius):
    """Convert Celsius to Fahrenheit"""
    return celsius * 9/5 + 32

def convert_ccf_therm(ccf):
    """Convert ccf to therm"""
    # This is the BTU factor from my latest gas bill
    return ccf * 1.137537

def convert_kcal_thermhours(kcal):
    """Convert kcal to therm/hr"""
    return kcal / 25200

def convert_lpm_gpm(lpm):
    """Convert LPM to GPM"""
    return lpm * 0.264172

def convert_m3_ccf(m3):
    """Convert m3 to ccf"""
    return m3 * 0.353147

def format_hex(data):
    """Format bytes as hex string"""
    return ' '.join(f'{b:02x}' for b in data)

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
            if DEBUG_MODE == DEBUG_ALL:
                # Dump raw packet for manual parsing
                print(f"Raw packet ({len(packet)} bytes): {format_hex(packet)}")

            # Check packet type
            if len(packet) >= 5:
                packet_id = [packet[2], packet[3], packet[4]]
                if packet_id == GAS_PACKET_ID:
                    await process_gas_packet(client, packet)
                elif packet_id == WATER_PACKET_ID:
                    await process_water_packet(client, packet)
                elif DEBUG_MODE == DEBUG_ALL:
                    print(f"  -> Unknown packet type: {format_hex(packet_id)}")
            
            if DEBUG_MODE == DEBUG_ALL:
                # Blank line between packets
                print("")

async def process_gas_packet(client, data):
    """Parse gas-related packet (Packet B)"""
    if len(data) < 6:
        return

    data_length = data[5]
    if len(data) < 7 + data_length:
        return

    if data_length < 18:
        return

    # Get raw data
    current_usage_kcal = data[23] << 8 | data[22]
    current_usage_thermhours = convert_kcal_thermhours(current_usage_kcal)
    total_usage_m3 = data[24] / 10.0
    total_usage_ccf = convert_m3_ccf(total_usage_m3)
    total_usage_therm = convert_ccf_therm(total_usage_ccf)

    if DEBUG_MODE == DEBUG_ALL:
        print(f"  Type: Gas")
        print(f"  Current Gas Usage: {current_usage_kcal} kcal")
        print(f"  Current Gas Usage: {current_usage_thermhours} therms")
        print(f"  Total Gas Usage: {total_usage_m3} m³")
        print(f"  Total Gas Usage: {total_usage_ccf} CCF")
        print(f"  Total Gas Usage: {total_usage_therm} therms")

    # Apply desired rounding
    total_usage_ccf = round(total_usage_ccf, 2)

    if homeAssistantState.gas_current_usage_kcal != current_usage_kcal:
        homeAssistantState.gas_current_usage_kcal = current_usage_kcal
        if DEBUG_MODE >= DEBUG_PUBLISH:
            print(f"  Publishing {MQTT_TOPIC_GAS_CURRENT_USAGE} with value '{current_usage_kcal}'")
        else:
            await client.publish(MQTT_TOPIC_GAS_CURRENT_USAGE, str(current_usage_kcal), retain=True)
    if homeAssistantState.gas_total_usage_ccf != total_usage_ccf:
        homeAssistantState.gas_total_usage_ccf = total_usage_ccf
        if DEBUG_MODE >= DEBUG_PUBLISH:
            print(f"  Publishing {MQTT_TOPIC_GAS_TOTAL_USAGE} with value '{total_usage_ccf}'")
        else:
            await client.publish(MQTT_TOPIC_GAS_TOTAL_USAGE, str(total_usage_ccf), retain=True)

async def process_water_packet(client, data):
    """Parse water-related packet (Packet A)"""
    if len(data) < 6:
        return
    
    data_length = data[5]
    if len(data) < 7 + data_length:
        return

    if data_length < 18:
        return

    # Get raw data
    system_power = (data[9] & 0x0f)
    set_temp_c = data[11] * 0.5
    set_temp_f = convert_c_f(set_temp_c)
    outlet_temp_c = data[12] * 0.5
    outlet_temp_f = convert_c_f(outlet_temp_c)
    inlet_temp_c = data[13] * 0.5
    inlet_temp_f = convert_c_f(inlet_temp_c)
    flow_rate_lpm = data[18] / 10.0
    flow_rate_gpm = convert_lpm_gpm(flow_rate_lpm)
    system_status = data[24]

    if DEBUG_MODE == DEBUG_ALL:
        print(f"  Type: Water")
        print(f"  System Power: {system_power}")
        print(f"  System Status: 0x{system_status:02x}")
        print(f"  Set Temperature: {set_temp_c}°C")
        print(f"  Set Temperature: {set_temp_f}°F")
        print(f"  Outlet Temperature: {outlet_temp_c}°C")
        print(f"  Outlet Temperature: {outlet_temp_f}°F")
        print(f"  Inlet Temperature (possible): {inlet_temp_c} °C")
        print(f"  Inlet Temperature (possible): {inlet_temp_f} °F")
        print(f"  Flow Rate: {flow_rate_lpm} LPM")
        print(f"  Flow Rate: {flow_rate_gpm} GPM")

    # Apply desired rounding
    outlet_temp_f = round(outlet_temp_f, 0)
    flow_rate_gpm = round(flow_rate_gpm, 1)

    if homeAssistantState.water_outlet_temp != outlet_temp_f:
        homeAssistantState.water_outlet_temp = outlet_temp_f
        if DEBUG_MODE >= DEBUG_PUBLISH:
            print(f"  Publishing {MQTT_TOPIC_WATER_OUTLET_TEMP} with value '{outlet_temp_f}'")
        else:
            await client.publish(MQTT_TOPIC_WATER_OUTLET_TEMP, str(outlet_temp_f), retain=True)
    if homeAssistantState.water_flow_rate != flow_rate_gpm:
        homeAssistantState.water_flow_rate = flow_rate_gpm
        if DEBUG_MODE >= DEBUG_PUBLISH:
            print(f"  Publishing {MQTT_TOPIC_WATER_FLOW_RATE} with value '{flow_rate_gpm}'")
        else:
            await client.publish(MQTT_TOPIC_WATER_FLOW_RATE, str(flow_rate_gpm), retain=True)

def read_packet(ser):
    """Read a complete packet from serial"""
    # Look for packet header
    while True:
        byte = ser.read(1)
        if not byte:
            return None
        
        if byte[0] == HEADER_BYTE_0:
            # Check second header byte
            byte2 = ser.read(1)
            if not byte2:
                return None
            
            if byte2[0] == HEADER_BYTE_1:
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
                packet = bytes([HEADER_BYTE_0, HEADER_BYTE_1]) + header_rest + remaining
                return packet

if __name__ == "__main__":
    asyncio.run(main())