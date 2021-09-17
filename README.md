# Low-Cost Level Sensor Project

## Contents
1. [Background](#markdown-header-1-background)
    1. [Proposal](#markdown-header-11-proposal)
    2. [Architecture](#markdown-header-12-architecture)
    3. [Hardware](#markdown-header-13-hardware)
2. [Sofware](#markdown-header-2-software)
3. [ESF Install](#markdown-header-3-esf-install)
4. [Acconeer Evaluation Kit Setup](#markdown-header-4-acconeer-evaluation-kit-setup)
    1. [Getting Started](#markdown-header-41-getting-started)
    2. [Port Opening](#markdown-header-42-port-opening)
    3. [Installing Dependencies](#markdown-header-43-installing-dependencies)
5. [Testing](#markdown-header-5-testing)
    1. [Directly Running the App](#markdown-header-51-directly-running-the-app)
    2. [Running the Tester](#markdown-header-52-running-the-tester)
6. [Python Connector Setup](#markdown-header-6-python-connector-setup)
    1. [Deployment Package Installation](#markdown-header-61-deployment-package-installation)
    2. [New Publisher Creation](#markdown-header-62-new-publisher-creation)
    3. [PyConnectorService Configuration](#markdown-header-63-pyconnector-configuration)
7. [Logging Data Locally](#markdown-header-7-logging-data-locally)
8. [Running](#markdown-header-8-running)
    1. [Data Warnings](#markdown-header-81-data-warnings)

Appendices

* [Appendix A: Sensor/Processing Configuration](#markdown-header-appendix-a-sensorprocessing-configuration)
* [Appendix B: Troubleshooting](#markdown-header-appendix-b-troubleshooting)

---

## 1 Background

### 1.1 Proposal
* Outcome: demonstration that a sensible water-related IoT application can be implemented using low-cost hardware in a short amount of time
* Application: off-grid IoT level sensor, in wastewater systems

### 1.2 Architecture
* Level sensor: antenna-on-chip radar sensor evaluation kit
* Raspberry Pi: running the above devkit and Everyware Software Framework (ESF)
* Cloud service: Everyware Cloud for device and data management
* Dashboarding: TBC (either Device Pilot or xCloud)

### 1.3 Hardware
* Raspberry Pi
* XR112 radar sensor module board
* XC112 connector board
* LH112 radar lens kit (more information at https://developer.acconeer.com/ > Documents and learning > LH112/LH122/LH132 > Getting Started Guide Lenses)

## 2 Software
The app is structured as outlined in [ESF/Kura Python Connector](https://xyleminc.atlassian.net/wiki/spaces/~220039589/pages/5254125195/ESF+Kura+Python+Connector); three callback functions `start()`, `get()`, and `stop()` are invoked as required to handle their respective events. The main detector software is called within `get()`, via the `process()` method (see `Processor` class in `processing.py`). The object presence detection / distance estimation can be split up into five main parts:

1. **Sweep averaging:** decrease the effect of noise by averaging `nbr_average` number of sweeps into one
2. **Threshold construction:** pick a threshold - either Fixed or CFAR (Constant False Alarm Rate; hasn't been tested yet)
3. **Peak identification:** compare the sweep to the threshold, and determine if there are any peaks above it
4. **Peak merging:** treat any neighbouring peaks too close together as one
5. **Peak sorting:** pick one of methods to choose the most important peak; so far Strongest seems to be the best choice

Here are the key things each event handler does, vaguely in order:

`start()`

* Set up logging
* Check if the XC112 streaming server is running, and if not, launch it via a shell script
* Configure the sensor and processor
* Connect to the socket client and carry out session setup
* Initialise Processor object

`get()`

* Create list to store sweep info
* Get sweep data, and `process()` it
* Publish any found peaks
* Warn of saturation or data quality issues

`stop()`

* Disconnect from the client
---

## 3 ESF Install
The below assumes your Raspberry Pi already has ESF installed and has been provisioned to connect to Xylem's Everyware Cloud. If not, see [Moving generic xGW's to EverywareCloud Environment](https://xyleminc.atlassian.net/wiki/spaces/XGW/pages/644220906/Moving+generic+xGW+s+to+EverywareCloud+Environment). You can find the right install file from the [ESF download page](https://www.eurotech.com/download/en/pb.aspx?pg=ESF), under *System Distribution* > *esf-raspberry-pi...rpm*

## 4 Acconeer Evaluation Kit Setup
If this is being read a while after summer 2021, you may want to check the official sources: [EVK Getting Started Guide](https://developer.acconeer.com/) (*Documents and learning* > *XC112/XR112*) and [Setting up your Raspberry Pi EVK](https://acconeer-python-exploration.readthedocs.io/en/latest/evk_setup/raspberry.html). After which, skip to the note on [Port Opening](#markdown-header-42-port-opening).

### 4.1 Getting Started
* In Raspberry Pi Configuration > Interfaces, ensure SSH, SPI, and I2C are enabled
* Make sure the latest version of Raspbian is being run, and install `libgpiod2`:
```
$ sudo apt-get update
$ sudo apt-get dist-upgrade
$ sudo apt install libgpiod2
```
* An extra line also needs to be added `/boot/config.txt`, after which the Raspberry Pi should be rebooted:
```
$ sudo sh -c 'echo "dtoverlay=spi0-1cs,cs0_pin=8" >> /boot/config.txt'
$ sudo reboot
```
* Install the radar sensor SDK for the Raspberry Pi: go to the [Acconeer Developer Site](https://developer.acconeer.com/) > *Software Downloads* > *XC112*, download ***acconeer_rpi_xc112***, and unzip.

### 4.2 Port Opening
ESF performs network management, and upon rebooting, you may find that the Pi seems to have lost its ability to conect to Wi-Fi. This can be fixed from the ESF console's Network management tab, but isn't really concerning if using ethernet (or cellular, as will probably be the case if/when this is deployed in the field).

Instead, venture forth to the **Firewall** tab just underneath Network and open up port 6110 on both tcp and udp protocols. 6110 is the default value, but you may want to verify this is the case: in `src/acconeer/exptool/client/links.py`, search for the `_PORT` variable.

Doing so enables the program to connect with Acconeer's streaming server rather than ESF going "Oh no stranger danger!".

### 4.3 Installing Dependencies
* Enter the root user environment through `su` in terminal, and install the packages dependencies in `requirements.txt`:
```
python3 -m pip install -U setuptools wheel
python3 -m pip install -U -r requirements.txt
```
Install the supplied `acconeer.exptool` library:
```
$ python3 -m pip install -U .` (note the full stop)
```
At the time you're reading this, the `acconeer.exptool` library may be out of date; the latest verison can be found at [Acconeer Exploration Tool](https://github.com/acconeer/acconeer-python-exploration) > `src/acconeer/exptool`.

## 5 Testing
There are two main ways you may verify that the app is working as expected. You can try either one of them, both, or if feeling especially brave, neither of them.

### 5.1 Directly Running the App
The first testing method is to directly invoke `app.py`, and call gets manually one by one:
```
$ cd client/
$ python3

>>> import app
>>> app.start(<get_interval: float>, <params: dict>)
>>> app.get(<counter: int>)
    .
    .
    .
>>> app.stop()
```
If everything goes well, you should see the GET data appear in the terminal, and in `sessions.log` as well (the log doesn't live-update though, so you might have to close and reopen it).

### 5.2 Running the Tester
Next, you might want to try using `tester.py`, which was kindly written by Christian, so go give him a pat on the back if you find this is your preferred method. 
```
$ cd client/
$ python3

>>> import tester
>>> tester.run('app.py', <get_interval_s: int>, <num_gets: int>, <params: dict>)
```
As with before, GET data should show up in both the terminal and `sessions.log`. Don't worry if the first one or two GETs return nothing; this is due to the delay caused by the combination of START still running and connecting to the streaming server. In the grand scheme of things, two empty GETs are basically nothing.

## 6 Python Connector Setup

### 6.1 Deployment Package Installation
* From the admin console's **Packages** manager, click *Install/Upgrade*
* Navigate to the `/kura/export` directory in this repository and choose the `.dpp` file
* After submitting this file, you should see a new service pop up in the sidebar called **PyConnectorSerivce**

### 6.2 New Publisher Creation
* In **Cloud Connections**, hit *New Pub/Sub* and select the ...*CloudPublisher* factory
* Name the new publisher, e.g. level.publisher
* Give the *Application ID* a relevant name, e.g. level
* Specify the *Application Topic*, ensuring that it begins with the application ID name, i.e. $messageType/$assetName
* Make sure *Kind of Message* is set to Data

### 6.3 PyConnectorService Configuration
* Going to **PyConnectorService**, select the newly created publisher under *CloudPublisher Target Filter* > *Select available targets*
* Pick your Python interpreter, which would be `python3` on a Raspberry Pi
* Enter the path of the python file to be executed, e.g. `/home/pi/low-cost-level-sensor/client/app.py`
* Enter your desired data interval
* Enter your parameters in a dictionary wrapped by `{}`
    * Required: `"ip_a"` specifiying the IP address of the target device
    * Recommended: `"device_name"` uniquely identifying the device that's pushing the data
    * Other items are optional, and configure either the sensor or processing (see the [Appendix A](#markdown-header-appendix-a-sensorprocessing-configuration))

## 7 Logging Data Locally
Note this step is optional. If you do need to operate without internet connection, ensure that the ip address you are connecting with is the loopback interface `127.0.0.1`.

* In the sidebar, under the Services heading, click the [+] button to add a new component
* Select the ...*H2DbServer* factory, and name it H2DbServer, then click into the newly created service
* Enable the DB server, specify it as a WEB type, and specify the following parameters: `-webPort 9123 -webAllowOthers -ifExists`
* In **Cloud Connections**, select the ...*CloudService* then DataService. Scroll to **Store Capacity** and set it to some large number like a million. This should suffice for a day or two of data collection.
* In **FireWall** > *Open Ports*, add a new entry. Specify the Port to be '9123', Protocol tcp, and Permitted Intercface Name 'eth0'

You can then visit 127.0.0.1:9123 to access the H2 console.

## 8 Running
* Restart the Kura bundle by applying any change under PyConnectorService, and data should begin being published to Everyware Cloud (if not already)
* In the event this doesn't seem to do anything, try hard-restarting the bundle via the ESF admin console: **Device** > *Bundles*. The relevant bundle should be found at/near the bottom and be named something like *com.xylem.xgw.bundle.pythonconnector*
* A third option is to reboot the Pi
* The data can be queried from Everyware Cloud, under the topic folder with the same name as your publisher's application ID

### 8.1 Data Warnings
In Everyware Cloud, you may come across a *warning* metric while querying distance readings. The first (and more common) would say '*Data saturated, reduce gain*', which, perhaps unsurprisingly, means the receiver has been saturated and gain should be decreased accordingly. I suggest beginning at gain=0.5 and in-/decrementing in steps of 0.1 to settle on thethe maximum value before data saturation.

If gain is too low, peaks might not be visible, or quantisation error would cause poor data quality. This allows us to smoothly segue into the other warning: '*Bad data quality, restart service*'. Again, pretty self-explanatory; merely restart the bundle, (check cable connections,) and it should disappear.

---

## Appendix A: Sensor/Processing Configuration
In PyConnectorService, the Parameters field takes a dictionary that can configure the program.

Information on sensor parameters can be found from Acconeer's documentation on their [Envelope Service](https://acconeer-python-exploration.readthedocs.io/en/latest/services/envelope.html#configuration-parameters). Note that some of the default values may be missing some linkage, e.g. `Profile.PROFILE_2` might need to be `et.configs.EnvelopeServiceConfig.Profile.PROFILE_2`.

Configurable processing paramaters can be found in `processing.py` under the `ProcessingConfiguration` class. `history_length_s` doesn't do anything here - it is a parameter for the Acconeer GUI, which isn't a part of this project. Theoretically, the processor parameter can be configured via their repsective `default_value` attributes, but I would recommend adjusting these via the ESF admin console. Or don't. I'm not your boss. And I probably don't work here by the time you're reading this.

## Appendix B: Troubleshooting
In the event that data publishing doesn't work, enter the superuser environment `su` in terminal and run `tester.py` to pick up any (and hopefully all) error messages. If issues with missing modules persist, the `acconeer.exptool` library may be out of date; the latest verison can be found at the [Acconeer Exploration Tool](https://github.com/acconeer/acconeer-python-exploration) repository. You may also want to have a look at the rest of the repository.