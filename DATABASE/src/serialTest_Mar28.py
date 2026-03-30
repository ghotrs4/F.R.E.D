import time 
import serial

serialPort = serial.Serial(
    port="/dev/rfcomm0", 
	baudrate=57600, 
	bytesize=8, 
	timeout=5, 
	stopbits=serial.STOPBITS_ONE
)

serialString = ""  # Used to hold data coming over UART
while 1:
    # Read data out of the buffer until a carraige return / new line is found
    serialString = serialPort.readline()

    # Print the contents of the serial data
    try:
        print(serialString.decode("UTF-8"))
    except:
        print("Error reading line...\n\n\n")
