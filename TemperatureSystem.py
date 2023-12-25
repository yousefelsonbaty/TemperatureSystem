from struct import unpack_from
import time
from machine import Pin, PWM, I2C
from time import sleep
from neopixel import NeoPixel
import i2ctemphum

SHTC3_REG_SLEEP                 = 0xB098    # Enter sleep mode
SHTC3_REG_WAKEUP                = 0x3517    # Wakeup mode
SHTC3_REG_SOFTRESET             = 0x805D    # Soft Reset
SHTC3_REG_READID                = 0xEFC8    # Read Out of ID Register

SHTC3_REG_NORMAL_T_F            = 0x7866    # Read T First And Clock Stretching Disabled In Normal Mode
SHTC3_REG_NORMAL_H_F            = 0x58E0    # Read H First And Clock Stretching Disabled In Normal Mode

SHTC3_REG_NORMAL_T_F_STRETCH    = 0x7CA2    # Read T First And Clock Stretching Enabled In Normal Mode
SHTC3_REG_NORMAL_H_F_STRETCH    = 0x5C24    # Read H First And Clock Stretching Enabled In Normal Mode

SHTC3_REG_LOWPOWER_T_F          = 0x609C    # Read T First And Clock Stretching Disabled In Lowpower Mode
SHTC3_REG_LOWPOWER_H_F          = 0x401A    # Read T First And Clock Stretching Disabled In Lowpower Mode

SHTC3_REG_LOWPOWER_T_F_STRETCH  = 0x6458    # Read T First And Clock Stretching Enabled In Lowpower Mode
SHTC3_REG_LOWPOWER_H_F_STRETCH  = 0x44DE    # Read T First And Clock Stretching Enabled In Lowpower Mode

SHTC3_NORMAL_MEAS               = [SHTC3_REG_NORMAL_T_F, SHTC3_REG_NORMAL_H_F]
SHTC3_NORMAL_MEAS_STRETCH       = [SHTC3_REG_NORMAL_T_F_STRETCH, SHTC3_REG_NORMAL_H_F_STRETCH]
SHTC3_LOWPOWER_MEAS             = [SHTC3_REG_LOWPOWER_T_F, SHTC3_REG_LOWPOWER_H_F]
SHTC3_LOWPOWER_MEAS_STRETCH     = [SHTC3_REG_LOWPOWER_T_F_STRETCH, SHTC3_REG_LOWPOWER_H_F_STRETCH]

SHTC3_MEAS                      = [SHTC3_NORMAL_MEAS, SHTC3_LOWPOWER_MEAS]
SHTC3_MEAS_STRETCH              = [SHTC3_NORMAL_MEAS_STRETCH, SHTC3_LOWPOWER_MEAS_STRETCH]

SHTC3_MEAS_ALL                  = [SHTC3_MEAS, SHTC3_MEAS_STRETCH]


class SHTC3(object):
    
    def __init__(self, i2c_num=0, i2c_scl=9, i2c_sda=8, address=0x70):
        self._address = address
        self.cmd = bytearray(2)
        self.buffer = bytearray(6)
        self.i2c = I2C(id=i2c_num, scl=Pin(i2c_scl, pull=Pin.PULL_UP), sda=Pin(i2c_sda, pull=Pin.PULL_UP), freq=100_000)
        
        # Avoid Distractions
        self.i2c.writeto(self._address, bytes([0, 0, 0]))
        print("SHTC3 ID = {:x}".format(self.read_id()))

    @staticmethod
    def crc8(buffer: bytearray) -> int:
        """verify the crc8 checksum"""
        crc = 0xFF
        for byte in buffer:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x31
                else:
                    crc = crc << 1
                print(crc)
        return crc & 0xFF  # return the bottom 8 bits

    def write_command(self, command: int):
        self.cmd[0] = command >> 8
        self.cmd[1] = command & 0xff
        self.i2c.writeto(self._address, self.cmd)

    def sleep(self):
        self.write_command(SHTC3_REG_SLEEP)
        time.sleep_us(300)

    def wakeup(self):
        self.write_command(SHTC3_REG_WAKEUP)
        time.sleep_us(300)

    def soft_reset(self):
        self.write_command(SHTC3_REG_SOFTRESET)
        time.sleep_us(300)

    def read_id(self):
        self.write_command(SHTC3_REG_READID)
        self.buffer = self.i2c.readfrom(self._address, 3)
        id = (self.buffer[0] << 8) + self.buffer[1]
        return id

    def measurement(self, hum_first=False, low_power_meas=False, stretch=False):
        command = SHTC3_MEAS_ALL[stretch][low_power_meas][hum_first]
        self.write_command(command)
        if low_power_meas:
            time.sleep_ms(2)
        else:
            time.sleep_ms(14)
        self.buffer = self.i2c.readfrom(self._address, 6)
        temp_data = self.buffer[hum_first * 3:hum_first * 3 + 2]
        temp_data_crc = self.buffer[hum_first * 3 + 2]
        hum_data = self.buffer[(not hum_first) * 3:(not hum_first) * 3 + 2]
        hum_data_crc = self.buffer[(not hum_first) * 3 + 2]

        if temp_data_crc != self.crc8(temp_data) or hum_data_crc != self.crc8(hum_data):
            print("crc error")
            print("buffer ={}".format(self.buffer))
            print("temp_data ={}".format(temp_data))
            print("temp_data_crc ={}".format(temp_data_crc))
            print("temp_data crc8 ={}".format(self.crc8(temp_data)))
            print("")
            return (0, 0)
        else:
            T_RAW = (temp_data[1] + (temp_data[0] << 8))
            RH_RAW = (hum_data[1] + (hum_data[0] << 8))
            T = (T_RAW * 175.0) / (1 << 16) - 45
            RH = (RH_RAW * 100.0) / (1 << 16)
            return (T, RH)

# Identify the GPIO pins
button = Pin(3, Pin.IN, Pin.PULL_UP)
print("Press the button to turn on the temperature system.")

max_lum = 100

rgb_led_num = 22
rgb_led_pin = Pin(rgb_led_num, Pin.OUT)
rgb_led = NeoPixel(rgb_led_pin, 1)

red = 0
green = 0
blue = 0

# Initialize buzzer
buzzer = PWM(Pin(12))
buzzer_duty = 30
buzzer_start_freq = 600
buzzer_end_freq = 1200

if __name__ == '__main__':
    sthc3 = SHTC3()
    sthc3.wakeup()
    temperature_system_on = False

    while True:
        # Check if button is pressed
        if button.value() == 0:
            if not temperature_system_on:
                # Read temperature from the sensor
                T, RH = sthc3.measurement(0, 0, 0)
                print("T = {:.2f}℃ , RH = {:.2f}%".format(T, RH))
                time.sleep(0.5)

                if round(T, 1) >= 28:
                    # Hot: Red
                    rgb_led[0] = (0, max_lum, 0)
                    rgb_led.write()
                    for cnt in range(buzzer_start_freq, buzzer_end_freq, 100):
                        buzzer.duty_u16(int(buzzer_duty * 65536))
                        buzzer.freq(cnt)
                        sleep(0.001)
                elif round(T, 1) <= 20:
                    # Cold: Blue
                    rgb_led[0] = (0, 0, max_lum)
                    rgb_led.write()
                    for cnt in range(buzzer_start_freq, buzzer_end_freq, 100):
                        buzzer.duty_u16(int(buzzer_duty * 65536))
                        buzzer.freq(cnt)
                        sleep(0.001)
                else:
                    # Warm: Green
                    rgb_led[0] = (max_lum, 0, 0)
                    rgb_led.write()
                    buzzer.duty_u16(0)

                temperature_system_on = True
            else:
                # Turn off temperature system
                rgb_led[0] = (0, 0, 0)  # Turn off RGB LED
                rgb_led.write()
                buzzer.duty_u16(0)  # Turn off buzzer
                temperature_system_on = False
                print("Temperature system is off")

sleep(0.1)
