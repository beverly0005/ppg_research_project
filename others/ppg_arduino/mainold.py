import serial,time,csv,os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
import time

plt.style.use('ggplot')

## initialize serial port (ttyUSB0 or ttyACM0) at 115200 baud rate
ser = serial.Serial('/dev/tty.usbserial-110',
                    baudrate=115200)
## set filename and delete it if it already exists
datafile_name = 'test_data.csv'
if os.path.isfile(datafile_name):
    os.remove(datafile_name)

## looping through serial prints and wait for restart of Arduino Uno
## with start word "MAX30102"

all_data = []
start_word = False
data_duration = 20  # seconds

start_time = None  # will store time when data collection starts

while True:
    try:
        curr_line = ser.readline()  # read line

        # Wait for Arduino to send start word
        if not start_word:
            if curr_line[0:-2] == b'MAX30102':
                start_word = True
                start_time = time.time()  # mark start time
                print("Program Start")
                print(f"Collecting Data for {data_duration} seconds...")
            continue

        # Append data while within the duration
        elapsed = time.time() - start_time
        print(f"Elapsed Time: {elapsed:.2f} seconds", end='\r')  # Print elapsed time
        if elapsed <= data_duration:
            all_data.append(curr_line)
        else:
            break 

    except KeyboardInterrupt:
        print("Keyboard Interrupt detected, stopping early...")
        break

print("Exited Loop. Collected {} samples.".format(len(all_data)))


# looping through data vector and removing bad data
# then, create vectors for time, red, and IR variables
t_vec,ir_vec,red_vec = [],[],[]
ir_prev,red_prev = 0.0,0.0
for ii in range(3,len(all_data)):
    try:
        curr_data = (all_data[ii][0:-2]).decode("utf-8").split(',')
    except:
        continue
    
    if len(curr_data)==3:

        if abs((float(curr_data[1])-ir_prev)/float(curr_data[1]))>1.01 or\
        abs((float(curr_data[2])-red_prev)/float(curr_data[2]))>1.01:
            continue
        
        t_vec.append(float(curr_data[0])/1000000.0)
        ir_vec.append(float(curr_data[1]))
        red_vec.append(float(curr_data[2]))
        ir_prev = float(curr_data[1])
        red_prev = float(curr_data[2])

print('Sample Rate: {0:2.1f}Hz'.format(1.0/np.mean(np.abs(np.diff(t_vec)))))

## saving data
with open(datafile_name,'a') as f:
    writer = csv.writer(f,delimiter=',')
    writer.writerow(['Time', 'IR', 'RED'])
    for t,x,y in zip(t_vec,ir_vec,red_vec):
        writer.writerow([t,x,y])
        
# ## plotting data vectors 
# fig = plt.figure(figsize=(12,8))
# ax1 = fig.add_subplot(111)
# ax1.set_xlabel('Time [s]',fontsize=24)
# ax1.set_ylabel('IR Amplitude',fontsize=24,color='#CE445D',labelpad=10)
# ax1.tick_params(axis='both',which='major',labelsize=16)
# plt1 = ax1.plot(t_vec,ir_vec,label='IR',color='#CE445D',linewidth=4)
# ax1_2 = plt.twinx()
# ax1_2.grid('off')
# ax1_2.set_ylabel('Red Amplitude',fontsize=24,color='#37A490',labelpad=10)
# ax1_2.tick_params(axis='y',which='major',labelsize=16)
# plt2 = ax1_2.plot(t_vec,red_vec,label='Red',color='#37A490',linewidth=4)
# lns = plt1+plt2
# labels = [l.get_label() for l in lns]
# ax1_2.legend(lns,labels,fontsize=16)
# plt.xlim([t_vec[0],t_vec[-1]])
# plt.tight_layout(pad=1.2)
# plt.savefig('max30102_python_example.png',dpi=300,facecolor=[252/255,252/255,252/255])
# plt.show()