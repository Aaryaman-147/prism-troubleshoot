# Manual review sheet

Score each plan against its reference. **Steps** 0-3: 3 = complete, correct, well ordered; 0 = wrong or invented. **Deeplink** 0-2: 2 = exact target screen, 1 = parent menu, 0 = wrong. Copy totals into TESTING.md's manual review table.


> **Retrieval validation note (post-review):** the manual scores below judge the actual plan outputs and are unchanged by catalog calibration. A separate whole-catalog run found 428/577 correct, 141 safe abstentions, 8 wrong-entry links, and **0 opposite-toggle errors**. The expanded 101-probe calibration recommends v1 / alpha 1.0 / floor 0.75 / margin 0.08 for a safety-first 51 correct / 0 wrong / 50 abstain result.

## 1: My TechCorp A15G tablet screen flashes and then goes completely blank whenever I tap to open an email in Gmail, and after it works for a short time it goes blank again.

**Reference:** Email server not responding on smartphone or tablet

### Email connection issue (score 0.69)

- **Verify Internet Connection** [auto] — It will confirm stable network connectivity  
  deeplink: Open the Wi-Fi settings page
  1. Swipe down from the top of the screen.  
     _source: If your phone doesn't have a dedicated Power button, swipe down from the top of the screen to open Quick settings, and then tap the Power icon._
  1. Touch and hold the Wi-Fi icon.  
     _source: Touch and hold the Wi-Fi icon to check your connection status._
  1. Check connection status in Quick settings.  
     _source: Touch and hold the Wi-Fi icon to check your connection status._
  1. Open Settings.  
     _source: If your phone doesn't have a dedicated Power button, swipe down from the top of the screen to open Quick settings, and then tap the Power icon._
  1. Tap Connections.  
     _source: Alternatively, go to Settings, tap Connections, and then tap Wi-Fi._
  1. Tap Wi-Fi to view network details.  
     **_no matching sentence in reference_**
  1. Load a webpage to test connectivity.  
     _source: To confirm your internet connection is working, try loading a webpage or performing a quick search._
- **Review Email Account Settings** [auto] — It will apply updated server configuration  
  deeplink: Open the your email settings page
  1. Open Settings.  
     _source: If your phone doesn't have a dedicated Power button, swipe down from the top of the screen to open Quick settings, and then tap the Power icon._
  1. Tap Accounts and backup.  
     _source: Step 3: Review Your Email Account Settings_
  1. Manage accounts.  
     _source: Step 3: Review Your Email Account Settings_
  1. Select your email account.  
     _source: Step 3: Review Your Email Account Settings_
  1. Remove the account from the device.  
     _source: In such cases, you may need to remove and re-add your email account to your phone to apply the new configuration._
  1. Add the account again using your credentials.  
     _source: In such cases, you may need to remove and re-add your email account to your phone to apply the new configuration._
- **Clear Email App Cache** [auto] — It will resolve temporary app glitches  
  deeplink: Open the Clear cache settings page
  1. Open Settings.  
     _source: If your phone doesn't have a dedicated Power button, swipe down from the top of the screen to open Quick settings, and then tap the Power icon._
  1. Tap Apps.  
     _source: Clearing the app's data will reset it to its original settings, effectively wiping it clean._
  1. Select your email app.  
     _source: Step 3: Review Your Email Account Settings_
  1. Tap Storage.  
     **_no matching sentence in reference_**
  1. Tap Clear cache.  
     _source: Tap Clear cache._
- **Check Email Access On A PC** [manual] — It will determine if issue is device  
  deeplink: none
  1. Open a web browser on a personal computer.  
     _source: First, try accessing your email on a personal computer._
  1. Navigate to your email provider's website.  
     _source: Sometimes, changes made by your email provider on their server can cause connection problems._
  1. Sign in with your email credentials.  
     _source: If you can sign in and access your email on a PC, your phone might not be connected to Wi-Fi or mobile data._
  1. Verify you can access your inbox.  
     _source: If you can sign in and access your email on a PC, your phone might not be connected to Wi-Fi or mobile data._
- **Clear Email App Data** [critical] — It will reset app to original settings  
  deeplink: none
  1. Open Settings.  
     _source: If your phone doesn't have a dedicated Power button, swipe down from the top of the screen to open Quick settings, and then tap the Power icon._
  1. Tap Apps.  
     _source: Clearing the app's data will reset it to its original settings, effectively wiping it clean._
  1. Select your email app.  
     _source: Step 3: Review Your Email Account Settings_
  1. Tap Storage.  
     **_no matching sentence in reference_**
  1. Tap Clear data.  
     _source: Tap Clear data, and then tap OK._
  1. Tap OK to confirm.  
     _source: If your phone doesn't have a dedicated Power button, swipe down from the top of the screen to open Quick settings, and then tap the Power icon._
- **Restart Phone In Safe Mode** [critical] — It will identify if third-party app causes  
  deeplink: none
  1. Press and hold the Power button.  
     _source: If your phone doesn't have a dedicated Power button, swipe down from the top of the screen to open Quick settings, and then tap the Power icon._
  1. Touch and hold the Power off icon.  
     _source: Touch and hold the Power off icon._
  1. Tap Safe mode when it appears.  
     _source: Tap Safe mode when it appears on the screen._
  1. Wait for device to restart.  
     _source: Step 5: Restart Your Phone in Safe Mode_
  1. Check if email issue persists in Safe mode.  
     _source: While in Safe mode, check if your email app is still experiencing issues._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 2 | n/a | Reference mismatch (complaint is Gmail blank screen, reference is email server). Plan follows the supplied reference; a few navigation steps are only loosely sourced. |

## 2: My Nexa X1 screen turns completely blank or white and no text appears when I search for a stock price or use the Quick Assist app, and it happens with other apps too.

**Reference:** Blank or black display on a smartphone or tablet

### Blank screen issue (score 0.85)

- **Check For Physical Damage** [manual] — It will identify any physical damage  
  deeplink: none
  1. Inspect the device for physical damage.  
     _source: First, please carefully inspect your phone or tablet, charger, and USB cable for any physical damage or signs of liquid exposure._
  1. Check charger and USB cable for damage.  
     _source: First, please carefully inspect your phone or tablet, charger, and USB cable for any physical damage or signs of liquid exposure._
  1. Remove cases or accessories covering ports.  
     _source: Please remove any cases or accessories that might be covering the charging port or buttons._
  1. Examine USB connections for corrosion or bent pins.  
     _source: Examine the USB connections for any corrosion or bent pins._
  1. Turn off the device.  
     _source: Please turn off your device and reconnect it to the appropriate charger until it is fully charged._
  1. Insert ejector tool into SIM/MicroSD tray hole.  
     _source: Insert the ejector tool into the small hole next to the SIM/MicroSD tray to eject the tray._
  1. Shine flashlight into SIM/MicroSD slot to check LDI.  
     _source: Shine a flashlight into the SIM/MicroSD slot._
- **Charge Device** [manual] — It will restore battery power level  
  deeplink: none
  1. Connect device to appropriate charger.  
     _source: Now, please connect your phone or tablet to its appropriate charger and let it charge for at least 1 hour._
  1. Let it charge for at least 1 hour.  
     _source: Now, please connect your phone or tablet to its appropriate charger and let it charge for at least 1 hour._
- **Force Restart Device** [critical] — It will reset the device power state  
  deeplink: none
  1. Press and hold Power button and Volume down button.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
  1. Hold for at least 20 seconds.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
- **Attempt Power On** [critical] — It will verify if device powers on  
  deeplink: none
  1. Disconnect device from charger.  
     _source: After charging, please disconnect the phone or tablet from the charger._
  1. Press and hold Power button for 15 to 20 seconds.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Grounded blank-screen checks in sensible order; no auto deeplinks. |

## 3: My Nexa Fold X1 screen went completely black, so I can't see or interact with the phone, and I'm unable to use Data Transfer or any other method to transfer my data.

**Reference:** Some things to check first

### Black screen recovery (score 0.82)

- **Charge Device** [manual] — It will restore power to the device  
  deeplink: none
  1. Connect the charger to the phone.  
     _source: Connect the mouse and keyboard to your phone or tablet using a USB adapter, and then navigate your device as needed._
  1. Plug the charger into a power outlet.  
     **_no matching sentence in reference_**
  1. Leave the device charging for at least one hour.  
     _source: You can also try forcing a restart by pressing and holding the Power and Volume down buttons for 20 seconds, and then charging the device for at least one hour._
- **Connect USB Peripherals** [manual] — It will allow device navigation via input  
  deeplink: none
  1. Connect a USB mouse to the phone using a USB adapter.  
     _source: Connect the mouse and keyboard to your phone or tablet using a USB adapter, and then navigate your device as needed._
  1. Connect a USB keyboard to the phone using a USB adapter.  
     _source: Connect the mouse and keyboard to your phone or tablet using a USB adapter, and then navigate your device as needed._
  1. Use the mouse and keyboard to navigate the device.  
     _source: Even if you cannot use the touchscreen on your device, you can access your data with a USB mouse and keyboard._
- **Enter Google Account** [manual] — It will verify identity to unlock device  
  deeplink: none
  1. Enter your Google account email.  
     _source: If you have multiple Google accounts and don't know which account was set up with the device, you can visit the Google Device Manager and check to see if the phone or tablet is in the list of devices registered to the ac_
  1. Enter your Google account password.  
     _source: If you have multiple Google accounts and don't know which account was set up with the device, you can visit the Google Device Manager and check to see if the phone or tablet is in the list of devices registered to the ac_
  1. Tap Sign in to proceed.  
     **_no matching sentence in reference_**
- **Force Restart Device** [critical] — It will reboot the system normally  
  deeplink: none
  1. Press and hold the Power button.  
     _source: You can also try forcing a restart by pressing and holding the Power and Volume down buttons for 20 seconds, and then charging the device for at least one hour._
  1. Press and hold the Volume down button.  
     _source: You can also try forcing a restart by pressing and holding the Power and Volume down buttons for 20 seconds, and then charging the device for at least one hour._
  1. Hold both buttons for 20 seconds.  
     _source: You can also try forcing a restart by pressing and holding the Power and Volume down buttons for 20 seconds, and then charging the device for at least one hour._
- **Access Recovery Menu** [critical] — It will initiate system recovery options  
  deeplink: none
  1. Press and hold the Power button.  
     _source: You can also try forcing a restart by pressing and holding the Power and Volume down buttons for 20 seconds, and then charging the device for at least one hour._
  1. Press and hold the Volume up button.  
     _source: You can also try forcing a restart by pressing and holding the Power and Volume down buttons for 20 seconds, and then charging the device for at least one hour._
  1. Hold both buttons until the recovery menu appears.  
     **_no matching sentence in reference_**

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 1 | n/a | Invented recovery actions: Enter Google Account and Access Recovery Menu are not supported by the reference; core charge/USB/force-restart steps are useful. |

## 4: My TechCorp Nexa A14/A15 screen suddenly went completely black on its own after about a month of use. It doesn't display anything, even when I try to turn it on.

**Reference:** Blank or black display on a smartphone or tablet

### Black screen issue (score 0.85)

- **Check For Physical Damage** [manual] — It will identify any physical damage  
  deeplink: none
  1. Inspect the device for physical damage.  
     _source: First, please carefully inspect your phone or tablet, charger, and USB cable for any physical damage or signs of liquid exposure._
  1. Check charger and USB cable for damage.  
     _source: First, please carefully inspect your phone or tablet, charger, and USB cable for any physical damage or signs of liquid exposure._
  1. Remove cases or accessories covering ports.  
     _source: Please remove any cases or accessories that might be covering the charging port or buttons._
  1. Examine USB connections for corrosion or bent pins.  
     _source: Examine the USB connections for any corrosion or bent pins._
  1. Eject SIM/MicroSD tray using ejector tool.  
     _source: Insert the ejector tool into the small hole next to the SIM/MicroSD tray to eject the tray._
  1. Shine flashlight into SIM/MicroSD slot to check LDI.  
     _source: Shine a flashlight into the SIM/MicroSD slot._
- **Charge Device** [manual] — It will replenish battery power  
  deeplink: none
  1. Connect device to appropriate charger.  
     _source: Now, please connect your phone or tablet to its appropriate charger and let it charge for at least 1 hour._
  1. Let device charge for at least 1 hour.  
     _source: Now, please connect your phone or tablet to its appropriate charger and let it charge for at least 1 hour._
- **Force Restart Device** [critical] — It will reset temporary software glitches  
  deeplink: none
  1. Press and hold Power button and Volume down button simultaneously.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
  1. Hold for at least 20 seconds to force restart.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
- **Attempt Power On** [critical] — It will verify if device powers on  
  deeplink: none
  1. Disconnect device from charger.  
     _source: After charging, please disconnect the phone or tablet from the charger._
  1. Press and hold Power button for 15 to 20 seconds.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
  1. Observe if TechCorp Nexa logo appears.  
     _source: You should see the TechCorp Nexa logo appear if it powers on successfully._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Grounded blank-screen workflow; safe checks precede restart/power-on. |

## 5: My tablet screen stays completely blank when I try to use Data Transfer to scan the QR code for transferring data from my Nexa X1 phone, so the transfer can't proceed.

**Reference:** Transfer Secure folder with Data Transfer

### Blank screen (score 0.81)

- **Open Data Transfer App** [manual] — It will launch the transfer interface  
  deeplink: none
  1. Swipe up on the Home screen to access the Apps screen.  
     _source: Swipe up on the Home screen to access the Apps screen._
  1. Tap the Search field.  
     _source: Tap the Search field, then enter and select Data Transfer to open the app._
  1. Enter.  
     _source: Tap the Search field, then enter and select Data Transfer to open the app._
  1. Select Data Transfer to open the app.  
     _source: Tap the Search field, then enter and select Data Transfer to open the app._
- **Position Devices Correctly** [manual] — It will enable proper QR code scanning  
  deeplink: none
  1. Place the tablet and phone within 4 inches of each other.  
     _source: Wireless connection: If you are using a wireless transfer, place the devices within 4 inches of each other._
  1. Ensure the tablet screen is visible and unobstructed.  
     **_no matching sentence in reference_**
- **Initiate Wireless Transfer** [manual] — It will display QR code  
  deeplink: none
  1. On the Nexa X1 phone, tap Receive on this phone.  
     _source: Wireless transfer: On the new device, tap Nexa/Android, then tap Wireless transfer._
  1. On the tablet, tap Send from this phone.  
     _source: Then, on the old device, tap Send from this phone_
  1. On the tablet, tap Nexa/Android.  
     _source: Wireless transfer: On the new device, tap Nexa/Android, then tap Wireless transfer._
  1. On the tablet, tap Wireless transfer.  
     _source: Wireless transfer: On the new device, tap Nexa/Android, then tap Wireless transfer._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 2 | n/a | Mostly grounded Data Transfer flow; device-positioning detail is only partially supported. |

## 6: My tablet's screen stays dark and only three app icons are lit while the rest are dark and won't open, so nothing loads on the screen and I can't use the device.

**Reference:** Use Multi window and App pairs on your smartphone or tablet

### Screen dark apps (score 0.7)

- **Open All Apps** [auto] — It will show all current apps  
  deeplink: View Apps screen grid
  1. Tap the All apps icon (the grid).  
     _source: Tap the All apps icon (the grid)._
- **Open Quick Access Panel** [manual] — It will access app shortcuts  
  deeplink: none
  1. Swipe left on the gray Quick Access panel handle.  
     _source: To find the panel, swipe left on the gray Quick Access panel handle, which is located on the right side of your screen._
  1. Located on the right side of your screen.  
     _source: To find the panel, swipe left on the gray Quick Access panel handle, which is located on the right side of your screen._
- **Drag App To Screen** [manual] — It will open app in split view  
  deeplink: none
  1. Drag and drop it to the left, right, top, or bottom of the screen.  
     _source: From here, you'll be able to see all of your current apps.To open an app in split screen view on Foldable devices, drag and drop it to the left, right, top, or bottom of the screen and then do the same for additional app_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 2 | Steps match the multi-window reference; Apps screen grid deeplink opens the intended screen. |

## 7: My new smartphone's main screen stays small and doesn't fill the whole display; I can't make it expand to full size and I've never seen this before.

**Reference:** Screen mirroring to your TechCorp TV

### Screen not full (score 0.8)

- **Adjust Aspect Ratio** [auto] — It will adjust screen scaling  
  deeplink: Open the Phone aspect settings page
  1. Open Quick settings panel.  
     _source: Open the Quick settings panel by swiping down from the top right of your screen._
  1. Tap Smart View.  
     _source: If you want to stream the TV's screen to your phone or tablet (if your TV supports it), navigate back to the Smart View main page, tap Other device → Phone, and then select your TV._
  1. Tap More options.  
     _source: In the TV's settings page, tap More options (the three vertical dots), and then tap Mirror screen (Smart View)._
  1. Tap Settings.  
     _source: In the TV's settings page, tap More options (the three vertical dots), and then tap Mirror screen (Smart View)._
  1. Tap Phone aspect ratio.  
     _source: Tap Settings, and then tap Phone aspect ratio._
  1. Select 16:9.  
     _source: Most TVs will look best with a 16:9 aspect ratio._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Aspect-ratio steps are grounded. Deeplink is dummy_positive placeholder, so n/a. |

## 8: My Nexa Fold X1 inner screen stopped working by itself; it shows no image and doesn't respond to touch, while the outer cover screen still works.

**Reference:** Access your smartphone's data if the screen does not respond

### Inner screen failure (score 0.81)

- **Connect Mouse** [manual] — It will enable screen navigation  
  deeplink: none
  1. Connect OTG adapter to phone.  
     _source: Some phones may have an OTG USB Connector that can be used to connect a mouse, but you can also use a DeX station or similar docking adapters._
  1. Connect mouse USB to adapter.  
     _source: Connect the adapter to your phone, and then connect the mouse's USB to the adapter._
- **Connect HDMI** [manual] — It will display screen on TV  
  deeplink: none
  1. Connect USB-C to HDMI adapter to phone.  
     _source: Connect the adapter to your phone, and then connect the mouse's USB to the adapter._
  1. Connect HDMI cable to adapter.  
     _source: Connect the adapter to your phone, and then connect the HDMI cable to the adapter._
  1. Connect HDMI cable to TV.  
     _source: Connect the adapter to your phone, and then connect the HDMI cable to the adapter._
  1. Power on TV.  
     _source: Power on your TV or monitor, and then select the input that your phone is connected to._
  1. Select input.  
     _source: Power on your TV or monitor, and then select the input that your phone is connected to._
- **Backup Data** [manual] — It will save your important files  
  deeplink: none
  1. Use mouse to navigate to Data Transfer.  
     _source: Even if you can no longer use the touchscreen, you can still access data, such as pictures or messages, using a USB mouse._
  1. Select files to back up.  
     _source: Now that you're connected, a mouse pointer will appear on screen, and you can click your way through backing up your data with Data Transfer or other methods._
  1. Initiate backup process.  
     **_no matching sentence in reference_**
- **Visit Service Center** [manual] — It will repair the screen issue  
  deeplink: none
  1. Go to TechCorp walk-in service center.  
     _source: Once you've backed up your data, please visit a TechCorp walk-in service center, or you can schedule a repair service online._
  1. Or schedule repair online.  
     _source: Once you've backed up your data, please visit a TechCorp walk-in service center, or you can schedule a repair service online._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 2 | n/a | Core USB/HDMI/service guidance is grounded; backup procedure adds a small unsupported detail. |

## 9: My TechCorp Nexa Fold X1 screen flickers and goes blank whenever I open it, so I can't see anything or access the settings, which stops me from using the phone.

**Reference:** Screen flickers when using the Camera on a smartphone

### Screen flickers (score 0.09)

- **Disable Super Steady Mode** [auto] — It will stop fast shutter use  
  deeplink: Open the icon settings page
  1. Open Camera app.  
     _source: Screen flickers when using the Camera on a smartphone._
  1. Tap Settings icon.  
     **_no matching sentence in reference_**
  1. Toggle off Super steady mode.  
     _source: Disable Super steady mode._
- **Increase Lighting** [manual] — It will reduce flicker effect  
  deeplink: none
  1. Move to a brighter environment.  
     **_no matching sentence in reference_**
  1. Turn on additional lights.  
     _source: Modern lighting, such as fluorescent or LED bulbs, flickers on and off rapidly._
- **Adjust Shutter Speed** [manual] — It will eliminate flicker artifact  
  deeplink: none
  1. Open Camera app.  
     _source: Screen flickers when using the Camera on a smartphone._
  1. Switch to Pro Video mode.  
     _source: Adjust shutter speed in Pro Video mode._
  1. Tap Shutter speed setting.  
     _source: While our eyes perceive this as steady light, a camera's fast shutter speed can sometimes capture this flicker, resulting in a flickering image or a black bar moving across your video._
  1. Select a slower speed than 1/125.  
     _source: If you are using Pro Video mode, you may notice this artifact when using shutter speeds faster than 1/125._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 2 | n/a | Reference mismatch (camera flicker article vs fold-screen complaint). Plan follows reference; lighting/settings navigation includes minor unsupported details. Placeholder deeplink is n/a. |

## 11: My Nexa X1 has a floating circle that constantly hovers on my screen and gives me quick shortcuts to recent apps, home, back, screen off, volume control, and more; I want to remove it.

**Reference:** Use Multi window and App pairs on your smartphone or tablet

### Remove floating shortcuts (score 0.9)

- **Edit Quick Access Panel** [manual] — It will remove unwanted shortcuts  
  deeplink: none
  1. Swipe left on the Quick Access panel handle.  
     _source: To find the panel, swipe left on the gray Quick Access panel handle, which is located on the right side of your screen._
  1. Tap the Edit icon.  
     _source: From any screen, swipe left on the Quick Access panel, and then tap the Edit icon (the pencil)._
  1. Tap the minus icon next to the shortcut to remove.  
     _source: Tap the minus icon next to the shortcuts you want to remove._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Grounded quick-access edit instruction; all-manual plan. |

## 12: My Nexa X1 screen stays blank and doesn't show any activation message or anything else when I turn it on after the carrier deactivated the old phone.

**Reference:** Blank or black display on a smartphone or tablet

### Blank screen issue (score 0.85)

- **Check For Physical Damage** [manual] — It will identify any physical damage  
  deeplink: none
  1. Inspect the device for physical damage.  
     _source: First, please carefully inspect your phone or tablet, charger, and USB cable for any physical damage or signs of liquid exposure._
  1. Check charger and USB cable for damage.  
     _source: First, please carefully inspect your phone or tablet, charger, and USB cable for any physical damage or signs of liquid exposure._
  1. Remove cases or accessories covering ports.  
     _source: Please remove any cases or accessories that might be covering the charging port or buttons._
  1. Examine USB connections for corrosion or bent pins.  
     _source: Examine the USB connections for any corrosion or bent pins._
  1. Turn off the device.  
     _source: Please turn off your device and reconnect it to the appropriate charger until it is fully charged._
  1. Insert ejector tool into SIM/MicroSD tray hole.  
     _source: Insert the ejector tool into the small hole next to the SIM/MicroSD tray to eject the tray._
  1. Shine flashlight into SIM/MicroSD slot to check LDI.  
     _source: Shine a flashlight into the SIM/MicroSD slot._
- **Charge Device** [manual] — It will replenish the battery charge  
  deeplink: none
  1. Connect device to appropriate charger.  
     _source: Now, please connect your phone or tablet to its appropriate charger and let it charge for at least 1 hour._
  1. Let it charge for at least 1 hour.  
     _source: Now, please connect your phone or tablet to its appropriate charger and let it charge for at least 1 hour._
- **Force Restart** [critical] — It will reset the device power state  
  deeplink: none
  1. Press and hold Power button and Volume down button.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
  1. Hold for at least 20 seconds.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
- **Attempt Power On** [critical] — It will test if device powers on  
  deeplink: none
  1. Disconnect device from charger.  
     _source: After charging, please disconnect the phone or tablet from the charger._
  1. Press and hold Power button for 15 to 20 seconds.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Grounded blank-screen workflow with safe ordering; no auto deeplinks. |

## 13: My smartphone's screen is completely cracked, it's a total crack and I can't use the device.

**Reference:** Cracked or bleeding screen on smartphone or tablet

### Cracked screen (score 0.9)

- **Authorized Repair Services** [manual] — It will repair your cracked screen  
  deeplink: none
  1. Visit Authorized Repair Services.  
     _source: Visit Authorized Repair Services for more information._
  1. Schedule a walk-in or mail-in repair.  
     _source: You can schedule a walk-in or mail-in repair to fix your cracked screen using Genuine Parts._
  1. Use Genuine Parts for the repair.  
     _source: You can schedule a walk-in or mail-in repair to fix your cracked screen using Genuine Parts._
- **Authorized Service Centers** [manual] — It will provide fast quality repairs  
  deeplink: none
  1. Visit a local Authorized Service Center.  
     _source: For fast, quality repairs you can trust and rely on, visit a local Authorized Service Center._
  1. Learn more about the cost of the repair.  
     _source: You can learn more about the cost of the repair._
  1. Receive trusted and reliable repair service.  
     _source: For fast, quality repairs you can trust and rely on, visit a local Authorized Service Center._
- **Extended Care Plan** [manual] — It will cover accidental damage  
  deeplink: none
  1. Check if you have an Extended Care Plan.  
     _source: If you have a Extended Care Plan service contract, it covers accidental damage from handling with a low deductible._
  1. Verify coverage for accidental damage from handling.  
     _source: If you have a Extended Care Plan service contract, it covers accidental damage from handling with a low deductible._
  1. Use the plan for low deductible repair or replacement.  
     _source: If you have a Extended Care Plan service contract, it covers accidental damage from handling with a low deductible._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Repair/service options are grounded and appropriate to the cracked-screen reference. |

## 14: My Nexa X1 Ultra only shows a blue (or black) screen with tiny text when I try to turn it on, and it won't start up. I tried holding the power button but it doesn't help.

**Reference:** Blank or black display on a smartphone or tablet

### Device not turning (score 0.85)

- **Check For Physical Damage** [manual] — It will identify any physical damage  
  deeplink: none
  1. Inspect the device for physical damage.  
     _source: First, please carefully inspect your phone or tablet, charger, and USB cable for any physical damage or signs of liquid exposure._
  1. Check charger and USB cable for damage.  
     _source: First, please carefully inspect your phone or tablet, charger, and USB cable for any physical damage or signs of liquid exposure._
  1. Remove cases or accessories covering ports.  
     _source: Please remove any cases or accessories that might be covering the charging port or buttons._
  1. Examine USB connections for corrosion or bent pins.  
     _source: Examine the USB connections for any corrosion or bent pins._
  1. Eject SIM/MicroSD tray using ejector tool.  
     _source: Insert the ejector tool into the small hole next to the SIM/MicroSD tray to eject the tray._
  1. Shine flashlight into SIM/MicroSD slot to check LDI.  
     _source: Shine a flashlight into the SIM/MicroSD slot._
- **Charge Device** [manual] — It will replenish the battery charge  
  deeplink: none
  1. Connect device to appropriate charger.  
     _source: Now, please connect your phone or tablet to its appropriate charger and let it charge for at least 1 hour._
  1. Let device charge for at least 1 hour.  
     _source: Now, please connect your phone or tablet to its appropriate charger and let it charge for at least 1 hour._
- **Force Restart Device** [critical] — It will reset the device power state  
  deeplink: none
  1. Press and hold Power button and Volume down button simultaneously.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
  1. Hold for at least 20 seconds.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
- **Attempt Power On** [critical] — It will verify if device powers on  
  deeplink: none
  1. Disconnect device from charger.  
     _source: After charging, please disconnect the phone or tablet from the charger._
  1. Press and hold Power button for 15 to 20 seconds.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Grounded blank/blue-screen checks and restart sequence; no auto deeplinks. |

## 15: My TechCorp X1 Ultra screen flashes extremely quickly (in milliseconds) whenever I plug in a charger, making the display unusable for a short period.

**Reference:** Blank or black display on a smartphone or tablet

### Screen flashing charger (score 0.6)

- **Check For Physical Damage** [manual] — It will identify any physical damage  
  deeplink: none
  1. Inspect the device for physical damage.  
     _source: First, please carefully inspect your phone or tablet, charger, and USB cable for any physical damage or signs of liquid exposure._
  1. Check the charger and USB cable for damage.  
     _source: First, please carefully inspect your phone or tablet, charger, and USB cable for any physical damage or signs of liquid exposure._
  1. Remove cases or accessories covering the charging port.  
     _source: Please remove any cases or accessories that might be covering the charging port or buttons._
  1. Examine USB connections for corrosion or bent pins.  
     _source: Examine the USB connections for any corrosion or bent pins._
  1. Ensure the USB connection feels secure with minimal movement.  
     _source: The USB connection should feel secure with minimal movement._
- **Check Liquid Damage Indicator** [manual] — It will detect liquid exposure  
  deeplink: none
  1. Turn off the phone or tablet.  
     _source: Turn off your phone or tablet._
  1. Insert the ejector tool into the SIM/MicroSD tray hole.  
     _source: Insert the ejector tool into the small hole next to the SIM/MicroSD tray to eject the tray._
  1. Eject the SIM/MicroSD tray.  
     _source: Insert the ejector tool into the small hole next to the SIM/MicroSD tray to eject the tray._
  1. Shine a flashlight into the SIM/MicroSD slot.  
     _source: Shine a flashlight into the SIM/MicroSD slot._
  1. Observe the Liquid Damage Indicator color.  
     _source: Next, let's check the Liquid Damage Indicator (LDI)._
- **Charge The Device** [manual] — It will replenish the battery charge  
  deeplink: none
  1. Connect the device to its appropriate charger.  
     _source: Now, please connect your phone or tablet to its appropriate charger and let it charge for at least 1 hour._
  1. Let it charge for at least 1 hour.  
     _source: Now, please connect your phone or tablet to its appropriate charger and let it charge for at least 1 hour._
- **Force A Restart** [critical] — It will reset the device state  
  deeplink: none
  1. Press and hold the Power button and Volume down button simultaneously.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
  1. Hold for at least 20 seconds.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
- **Attempt To Power On** [critical] — It will verify device functionality  
  deeplink: none
  1. Disconnect the device from the charger.  
     _source: After charging, please disconnect the phone or tablet from the charger._
  1. Press and hold the Power button for 15 to 20 seconds.  
     _source: Press and hold both the Power button (or Side button) and the Volume down button simultaneously for at least 20 seconds._
  1. Observe if the TechCorp Nexa logo appears.  
     _source: You should see the TechCorp Nexa logo appear if it powers on successfully._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Grounded physical/liquid-damage, charge, restart and power-on sequence. |

## 18: My Nexa A14 screen looks distorted right after I received the phone, and I need a diagnostic test.

**Reference:** Screen does not rotate on smartphone or tablet

### Screen rotation issue (score 0.78)

- **Adjust Screen Orientation Settings** [auto] — It will enable auto rotate mode  
  deeplink: View Rotate to landscape mode
  1. Swipe down from the top of the screen with two fingers.  
     _source: Using two fingers, swipe down from the top of the screen to open the Quick settings panel._
  1. Tap the screen orientation icon.  
     _source: Locate the screen orientation icon._
  1. Select Auto rotate.  
     _source: Auto rotate: This setting allows your device's screen orientation to automatically adjust and rotate when you turn your device._
- **Check For Physical Damage** [manual] — It will identify any physical damage  
  deeplink: none
  1. Inspect the screen for cracks or damage.  
     _source: Please check for any cracks or other damage to the screen._
- **Contact Customer Support** [manual] — It will arrange for repair service  
  deeplink: none
  1. Contact Customer Support.  
     _source: If the device's screen is damaged, please contact Customer Support to set up service._
  1. Request service for screen issue.  
     _source: If the issue persists after completing all the above steps, please contact Customer Support to arrange for service_
- **Update Device Software** [critical] — It will install latest software updates  
  deeplink: none
  1. Open Settings.  
     _source: Using two fingers, swipe down from the top of the screen to open the Quick settings panel._
  1. Tap Software update.  
     _source: Update Device Software_
  1. Tap Download and install.  
     **_no matching sentence in reference_**
- **Restart Your Device** [critical] — It will refresh system processes  
  deeplink: none
  1. Press and hold the Power button.  
     _source: On devices with a Power button: Press and hold the Power button, then tap Restart._
  1. Tap Restart.  
     _source: On devices with a Power button: Press and hold the Power button, then tap Restart._
  1. Tap Restart again to confirm.  
     _source: On devices with a Power button: Press and hold the Power button, then tap Restart._
- **Perform Factory Data Reset** [critical] — It will restore device to factory settings  
  deeplink: none
  1. Open Settings.  
     _source: Using two fingers, swipe down from the top of the screen to open the Quick settings panel._
  1. Search for.  
     _source: Navigate to Settings, search for and select Factory data reset, and then tap Factory data reset again._
  1. Select Factory data reset.  
     _source: Navigate to Settings, search for and select Factory data reset, and then tap Factory data reset again._
  1. Tap Factory data reset.  
     _source: Navigate to Settings, search for and select Factory data reset, and then tap Factory data reset again._
  1. Tap Reset.  
     _source: Navigate to Settings, search for and select Factory data reset, and then tap Factory data reset again._
  1. Enter credentials if prompted.  
     _source: If you have a security lock enabled, you will be prompted to enter your credentials._
  1. Tap Delete all.  
     _source: Afterward, tap Delete all._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 2 | 1 | Reference mismatch (distorted-screen complaint paired with rotation article). Plan follows reference; one software-update substep is unsupported. Orientation deeplink is related but not the exact Auto rotate control. |

## 19: My Nexa X1 screen inputs are delayed and the touch responsiveness is laggy, causing a noticeable delay when I try to interact with the phone.

**Reference:** Touchscreen issues on a smartphone or tablet

### Touchscreen delay (score 0.85)

- **Enable Touch Sensitivity** [auto] — It will improve touch detection through films  
  deeplink: Enable Touch sensitivity
  1. Open Settings.  
     _source: For devices with a Side button: Swipe down from the top of the screen with two fingers to open the Quick settings panel._
  1. Tap Display.  
     _source: To turn off this feature, navigate to Settings, tap Display, and then tap the switch next to Touch sensitivity to disable it._
  1. Tap the Touch sensitivity switch to enable it.  
     _source: To turn off this feature, navigate to Settings, tap Display, and then tap the switch next to Touch sensitivity to disable it._
- **Disable Full Screen Gestures** [auto] — It will prevent gesture misinterpretation of touches  
  deeplink: Open the Navigation bar settings page
  1. Open Settings.  
     _source: For devices with a Side button: Swipe down from the top of the screen with two fingers to open the Quick settings panel._
  1. Tap Display.  
     _source: To turn off this feature, navigate to Settings, tap Display, and then tap the switch next to Touch sensitivity to disable it._
  1. Tap Navigation bar.  
     _source: Go to Settings, tap Display, and then tap Navigation bar._
  1. Select Buttons.  
     _source: Select Buttons to turn off full screen gestures._
- **Remove Screen Protector** [manual] — It will eliminate interference from accessories  
  deeplink: none
  1. Peel off the screen protector.  
     _source: This is especially true if there's dust or air trapped under the protector, if you have more than one protective film on the screen, or if the film is peeling at the edges._
  1. Clean the screen with a microfiber cloth.  
     _source: To clean your device, gently wipe the front and back with a lint-free, soft microfiber cloth or a camera lens cleaning cloth._
- **Restart Device** [critical] — It will refresh system processes and memory  
  deeplink: none
  1. Press and hold the Power button.  
     _source: For devices with a Power button: Press and hold the Power button, then tap Restart._
  1. Tap Restart.  
     _source: For devices with a Power button: Press and hold the Power button, then tap Restart._
  1. Tap Restart again to confirm.  
     _source: For devices with a Power button: Press and hold the Power button, then tap Restart._
- **Check For Software Updates** [critical] — It will install performance and bug fixes  
  deeplink: none
  1. Open Settings.  
     _source: For devices with a Side button: Swipe down from the top of the screen with two fingers to open the Quick settings panel._
  1. Tap Software update.  
     _source: Keeping your device's software up to date is important for smooth performance._
  1. Tap Download and install.  
     _source: Safe mode can help us identify if a recently installed third-party app is causing the problem._
- **Enter Safe Mode** [critical] — It will isolate third-party app interference  
  deeplink: none
  1. Press and hold the Power button.  
     _source: For devices with a Power button: Press and hold the Power button, then tap Restart._
  1. Tap and hold Power off.  
     _source: For devices with a Power button: Press and hold the Power button, then tap Restart._
  1. Tap Safe mode.  
     _source: Touch and hold Power off, then tap Safe mode._
- **Factory Data Reset** [critical] — It will restore device to original software  
  deeplink: none
  1. Open Settings.  
     _source: For devices with a Side button: Swipe down from the top of the screen with two fingers to open the Quick settings panel._
  1. Tap General management.  
     _source: Tap General management._
  1. Tap Reset.  
     _source: Swipe to and tap Reset._
  1. Tap Factory data reset.  
     _source: Tap Factory data reset._
  1. Swipe to.  
     _source: For devices with a Side button: Swipe down from the top of the screen with two fingers to open the Quick settings panel._
  1. Tap Reset.  
     _source: Swipe to and tap Reset._
  1. Tap Delete all.  
     _source: Tap Delete all._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 1 | 0 | Touch Sensitivity action contradicts its cited reference: the reference says disable it, while the plan enables it. Deeplink performs the same opposite toggle; remaining steps are useful. |

## S1-01: My phone gets really hot when I'm just browsing the internet, even with low brightness.

**Reference:** Device overheating during light use

### Phone overheating (score 0.85)

- **Background Usage Limits** [auto] — It will reduce background app activity  
  deeplink: Enable Put unused apps to sleep
  1. Open Settings.  
     _source: Then open Settings, tap Display, tap Motion smoothness, and select Standard_
  1. Tap Battery.  
     _source: Open Settings, tap Battery, tap Background usage limits, and turn on Put unused apps to sleep._
  1. Tap Background usage limits.  
     _source: Open Settings, tap Battery, tap Background usage limits, and turn on Put unused apps to sleep._
  1. Turn on Put unused apps to sleep.  
     _source: Open Settings, tap Battery, tap Background usage limits, and turn on Put unused apps to sleep._
- **Motion Smoothness** [auto] — It will lower screen refresh rate  
  deeplink: Adjust Motion smoothness
  1. Open Settings.  
     _source: Then open Settings, tap Display, tap Motion smoothness, and select Standard_
  1. Tap Display.  
     _source: Then open Settings, tap Display, tap Motion smoothness, and select Standard_
  1. Tap Motion smoothness.  
     _source: Then open Settings, tap Display, tap Motion smoothness, and select Standard_
  1. Select Standard.  
     _source: Then open Settings, tap Display, tap Motion smoothness, and select Standard_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 2 | Both overheating mitigations are grounded; deeplinks match unused-app sleep and Motion smoothness. |

## S1-02: Bluetooth keeps disconnecting from my car every few minutes during a call.

**Reference:** Bluetooth disconnects from car

### Bluetooth disconnecting (score 0.9)

- **Unpair Car** [auto] — It will remove the car pairing  
  deeplink: Open the Unpair settings page
  1. Open Settings.  
     _source: Open Settings, tap Connections, tap Bluetooth, tap the gear icon next to the car, and tap Unpair._
  1. Tap Connections.  
     _source: Open Settings, tap Connections, tap Bluetooth, tap the gear icon next to the car, and tap Unpair._
  1. Tap Bluetooth.  
     _source: Open Settings, tap Connections, tap Bluetooth, tap the gear icon next to the car, and tap Unpair._
  1. Tap the gear icon next to the car.  
     _source: Open Settings, tap Connections, tap Bluetooth, tap the gear icon next to the car, and tap Unpair._
  1. Tap Unpair.  
     _source: Open Settings, tap Connections, tap Bluetooth, tap the gear icon next to the car, and tap Unpair._
- **Pair Car** [manual] — It will reconnect the car Bluetooth  
  deeplink: none
  1. Open the car's Bluetooth menu.  
     _source: Open Settings, tap Connections, tap Bluetooth, tap the gear icon next to the car, and tap Unpair._
  1. Select your phone to pair.  
     _source: Then pair the car again from the car's menu_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Forget/re-pair Bluetooth flow is grounded; auto link is a dummy_positive placeholder. |

## S1-03: The fingerprint sensor stopped recognizing my thumb after the last update.

**Reference:** Fingerprint not recognized after update

### Fingerprint not recognized (score 0.95)

- **Security And Privacy** [auto] — It will access biometric settings  
  deeplink: Open the Security settings page
  1. Open Settings.  
     _source: Open Settings, tap Security and privacy, tap Biometrics, tap Fingerprints, remove the existing fingerprint, and add it again_
  1. Tap Security and privacy.  
     _source: Open Settings, tap Security and privacy, tap Biometrics, tap Fingerprints, remove the existing fingerprint, and add it again_
- **Remove Fingerprint** [auto] — It will delete the existing fingerprint  
  deeplink: View Fingerprint unlock
  1. Remove the existing fingerprint.  
     _source: Open Settings, tap Security and privacy, tap Biometrics, tap Fingerprints, remove the existing fingerprint, and add it again_
- **Fingerprints** [manual] — It will list registered fingerprints  
  deeplink: none
  1. Tap Biometrics.  
     _source: Open Settings, tap Security and privacy, tap Biometrics, tap Fingerprints, remove the existing fingerprint, and add it again_
  1. Tap Fingerprints.  
     _source: Open Settings, tap Security and privacy, tap Biometrics, tap Fingerprints, remove the existing fingerprint, and add it again_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 1 | Fingerprint flow is grounded. Deeplink opens Fingerprint unlock area, but removal still requires navigation/action within that screen. |

## S1-04: Notifications are delayed by several minutes, sometimes I miss calls entirely.

**Reference:** Delayed notifications

### Delayed Notifications (score 0.85)

- **Battery Optimization** [auto] — It will prevent battery from delaying alerts  
  deeplink: Open the Battery settings page
  1. Open Settings.  
     _source: Open Settings, tap Apps, select the affected app, tap Battery, and choose Unrestricted_
  1. Tap Apps.  
     _source: Open Settings, tap Apps, select the affected app, tap Battery, and choose Unrestricted_
  1. Select the affected app.  
     _source: Open Settings, tap Apps, select the affected app, tap Battery, and choose Unrestricted_
  1. Tap Battery.  
     _source: Open Settings, tap Apps, select the affected app, tap Battery, and choose Unrestricted_
  1. Choose Unrestricted.  
     _source: Open Settings, tap Apps, select the affected app, tap Battery, and choose Unrestricted_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Battery-optimization steps are grounded; link is a placeholder settings page. |

## S1-05: My keyboard keeps switching to a different language on its own.

**Reference:** Keyboard language switching

### Keyboard language switching (score 0.9)

- **Keyboard** [auto] — It will open keyboard settings  
  deeplink: View Magnification Settings
  1. Open Settings.  
     _source: Open Settings, tap General management, tap Keyboard, tap Languages and types, and remove languages you do not use_
  1. Tap General management.  
     _source: Open Settings, tap General management, tap Keyboard, tap Languages and types, and remove languages you do not use_
  1. Tap Keyboard.  
     _source: Open Settings, tap General management, tap Keyboard, tap Languages and types, and remove languages you do not use_
- **Languages And Types** [manual] — It will show language preferences  
  deeplink: none
  1. Tap Languages and types.  
     _source: Open Settings, tap General management, tap Keyboard, tap Languages and types, and remove languages you do not use_
- **Remove Unused Languages** [manual] — It will prevent unwanted language switches  
  deeplink: none
  1. Remove languages you do not use.  
     _source: Open Settings, tap General management, tap Keyboard, tap Languages and types, and remove languages you do not use_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 0 | Steps correctly follow keyboard language settings, but the auto deeplink says View Magnification Settings, which is the wrong screen. |

## S1-06: Photos I take look blurry and grainy even in good lighting.

**Reference:** Blurry camera photos

### Blurry Photos (score 0.85)

- **Reset Camera Settings** [auto] — It will restore default camera configurations  
  deeplink: Open the icon settings page
  1. Open the Camera app.  
     _source: Then open the Camera app, tap the settings icon, and tap Reset settings_
  1. Tap the settings icon.  
     _source: Then open the Camera app, tap the settings icon, and tap Reset settings_
  1. Tap Reset settings.  
     _source: Then open the Camera app, tap the settings icon, and tap Reset settings_
- **Clean Lens** [manual] — It will remove smudges and dirt  
  deeplink: none
  1. Use a soft cloth.  
     _source: Clean the rear lens with a soft cloth._
  1. Gently wipe the rear camera lens.  
     **_no matching sentence in reference_**

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 1 | n/a | Reset-camera steps are grounded, but Clean Lens is an invented action: its only step has no matching reference sentence. |

## S1-07: The phone randomly restarts itself once or twice a day.

**Reference:** Random restarts

### Random restarts (score 0.85)

- **Disable Auto Restart** [auto] — It will prevent scheduled automatic restarts  
  deeplink: Disable Auto Restart
  1. Open Settings.  
     _source: Open Settings, tap Device care, tap the three-dot menu, tap Automation, and turn off Auto restart at set times._
  1. Tap Device care.  
     _source: Open Settings, tap Device care, tap the three-dot menu, tap Automation, and turn off Auto restart at set times._
  1. Tap the three-dot menu.  
     _source: Open Settings, tap Device care, tap the three-dot menu, tap Automation, and turn off Auto restart at set times._
  1. Tap Automation.  
     _source: Open Settings, tap Device care, tap the three-dot menu, tap Automation, and turn off Auto restart at set times._
  1. Turn off Auto restart at set times.  
     _source: Open Settings, tap Device care, tap the three-dot menu, tap Automation, and turn off Auto restart at set times._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 2 | Grounded Auto restart fix; deeplink performs the intended Disable Auto Restart action. |

## S1-08: Wi-Fi connects but there's no internet, and it happens only at my office.

**Reference:** Wi-Fi connected without internet

### Wi-Fi no internet (score 0.86)

- **Forget Network** [auto] — It will clear saved network credentials  
  deeplink: Open the Forget settings page
  1. Open Settings.  
     _source: Open Settings, tap Connections, tap Wi-Fi, tap the gear icon next to the network, tap Forget, then rejoin the network_
  1. Tap Connections.  
     _source: Open Settings, tap Connections, tap Wi-Fi, tap the gear icon next to the network, tap Forget, then rejoin the network_
  1. Tap Wi-Fi.  
     _source: Open Settings, tap Connections, tap Wi-Fi, tap the gear icon next to the network, tap Forget, then rejoin the network_
  1. Tap the gear icon next to the network.  
     _source: Open Settings, tap Connections, tap Wi-Fi, tap the gear icon next to the network, tap Forget, then rejoin the network_
  1. Tap Forget.  
     _source: Open Settings, tap Connections, tap Wi-Fi, tap the gear icon next to the network, tap Forget, then rejoin the network_
- **Rejoin Network** [auto] — It will reconnect to the Wi-Fi network  
  deeplink: Open the Connect settings page
  1. Open Settings.  
     _source: Open Settings, tap Connections, tap Wi-Fi, tap the gear icon next to the network, tap Forget, then rejoin the network_
  1. Tap Connections.  
     _source: Open Settings, tap Connections, tap Wi-Fi, tap the gear icon next to the network, tap Forget, then rejoin the network_
  1. Tap Wi-Fi.  
     _source: Open Settings, tap Connections, tap Wi-Fi, tap the gear icon next to the network, tap Forget, then rejoin the network_
  1. Select the network from the list.  
     _source: Open Settings, tap Connections, tap Wi-Fi, tap the gear icon next to the network, tap Forget, then rejoin the network_
  1. Enter password if required.  
     **_no matching sentence in reference_**
  1. Tap Connect.  
     _source: Wi-Fi connected without internet._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Forget and rejoin flow is grounded; password entry is a harmless implied step. Links are placeholders. |

## S1-09: Voice calls sound muffled and the other person says I sound far away.

**Reference:** Muffled call audio

### Muffled call audio (score 0.9)

- **Turn Off Noise Reduction** [auto] — It will disable audio filtering  
  deeplink: Open the three-dot settings page
  1. Open the Phone app.  
     _source: Open the Phone app, tap the three-dot menu, tap Settings, and turn off Noise reduction_
  1. Tap the three-dot menu.  
     _source: Open the Phone app, tap the three-dot menu, tap Settings, and turn off Noise reduction_
  1. Tap Settings.  
     _source: Open the Phone app, tap the three-dot menu, tap Settings, and turn off Noise reduction_
  1. Turn off Noise reduction.  
     _source: Open the Phone app, tap the three-dot menu, tap Settings, and turn off Noise reduction_
- **Remove Phone Case** [manual] — It will clear microphone blockage  
  deeplink: none
  1. Remove the phone case.  
     _source: Remove the phone case and clean the microphone hole._
- **Clean Microphone Hole** [manual] — It will remove debris blocking mic  
  deeplink: none
  1. Clean the microphone hole.  
     _source: Remove the phone case and clean the microphone hole._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Noise-reduction, case and microphone checks are grounded; auto link is a placeholder. |

## S1-10: The clock and calendar show the wrong time zone after I landed from a trip.

**Reference:** Wrong time zone after travel

### Wrong time zone (score 0.95)

- **Date And Time** [auto] — It will enable automatic time zone  
  deeplink: Open the Date settings page
  1. Open Settings.  
     _source: Open Settings, tap General management, tap Date and time, and turn on Automatic time zone_
  1. Tap General management.  
     _source: Open Settings, tap General management, tap Date and time, and turn on Automatic time zone_
  1. Tap Date and time.  
     _source: Open Settings, tap General management, tap Date and time, and turn on Automatic time zone_
  1. Turn on Automatic time zone.  
     _source: Open Settings, tap General management, tap Date and time, and turn on Automatic time zone_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Date/time-zone navigation is grounded; link is a placeholder. |

## S2-11: Split-screen mode keeps closing one of the two apps by itself after about a minute.

**Reference:** Split screen closes an app

### Split screen closes (score 0.8)

- **Clean Memory** [auto] — It will free up system memory  
  deeplink: Open the Clean now settings page
  1. Open Settings.  
     _source: Then open Settings, tap Advanced features, tap Labs, and turn on Multi window for all apps_
  1. Tap Device care.  
     _source: Open Settings, tap Device care, tap Memory, and tap Clean now._
  1. Tap Memory.  
     _source: Open Settings, tap Device care, tap Memory, and tap Clean now._
  1. Tap Clean now.  
     _source: Open Settings, tap Device care, tap Memory, and tap Clean now._
- **Enable Multi Window** [auto] — It will prevent apps from closing unexpectedly  
  deeplink: Enable Multi window for all apps
  1. Open Settings.  
     _source: Then open Settings, tap Advanced features, tap Labs, and turn on Multi window for all apps_
  1. Tap Advanced features.  
     _source: Then open Settings, tap Advanced features, tap Labs, and turn on Multi window for all apps_
  1. Tap Labs.  
     _source: Then open Settings, tap Advanced features, tap Labs, and turn on Multi window for all apps_
  1. Turn on Multi window for all apps.  
     _source: Then open Settings, tap Advanced features, tap Labs, and turn on Multi window for all apps_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 2 | Clean-memory and Multi window steps are grounded; scored deeplink exactly enables Multi window (other link is placeholder). |

## S2-12: The always-on display shows the wrong battery percentage compared to the lock screen.

**Reference:** Always On Display battery mismatch

### Battery mismatch fix (score 0.9)

- **Always On Display** [critical] — It will refresh the AOD status information  
  deeplink: none
  1. Open Settings.  
     _source: Open Settings, tap Lock screen and AOD, tap Always On Display, turn it off, then turn it back on_
  1. Tap Lock screen and AOD.  
     _source: Open Settings, tap Lock screen and AOD, tap Always On Display, turn it off, then turn it back on_
  1. Tap Always On Display.  
     _source: Open Settings, tap Lock screen and AOD, tap Always On Display, turn it off, then turn it back on_
  1. Turn it off.  
     _source: Open Settings, tap Lock screen and AOD, tap Always On Display, turn it off, then turn it back on_
  1. Turn it back on.  
     _source: Open Settings, tap Lock screen and AOD, tap Always On Display, turn it off, then turn it back on_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | AOD off/on refresh exactly follows the reference; no auto action. |

## S2-13: My phone won't charge past 80% since I turned on a battery protection feature I don't remember enabling.

**Reference:** Charging stops at 80%

### Charging stops (score 0.95)

- **Tap Battery Protection** [auto] — It will show protection options  
  deeplink: Open the Battery protection settings page
  1. Open Settings.  
     _source: Open Settings, tap Battery, tap Battery protection, and select Basic or turn protection off_
  1. Tap Battery.  
     _source: Open Settings, tap Battery, tap Battery protection, and select Basic or turn protection off_
  1. Tap Battery protection.  
     _source: Open Settings, tap Battery, tap Battery protection, and select Basic or turn protection off_
- **Select Basic Or Turn Off** [manual] — It will disable the 80% charge limit  
  deeplink: none
  1. Select Basic or turn protection off.  
     _source: Open Settings, tap Battery, tap Battery protection, and select Basic or turn protection off_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Battery protection navigation and selection are grounded; auto link is a placeholder. |

## S2-14: The screen recorder captures video but no system audio, only my microphone.

**Reference:** Screen recorder has no media audio

### No system audio (score 0.95)

- **Tap Screenshots And Screen Recordings** [auto] — It will open screen recorder settings  
  deeplink: View Screenshots and screen recordings
  1. Open Settings.  
     _source: Open Settings, tap Advanced features, tap Screenshots and screen recordings, tap Screen recorder settings, tap Sound, and select Media sounds or Media sounds and mic_
  1. Tap Advanced features.  
     _source: Open Settings, tap Advanced features, tap Screenshots and screen recordings, tap Screen recorder settings, tap Sound, and select Media sounds or Media sounds and mic_
  1. Tap Screenshots and screen recordings.  
     _source: Open Settings, tap Advanced features, tap Screenshots and screen recordings, tap Screen recorder settings, tap Sound, and select Media sounds or Media sounds and mic_
- **Tap Screen Recorder Settings** [auto] — It will open recorder configuration  
  deeplink: Open the recorder settings page
  1. Tap Screen recorder settings.  
     _source: Open Settings, tap Advanced features, tap Screenshots and screen recordings, tap Screen recorder settings, tap Sound, and select Media sounds or Media sounds and mic_
- **Select Media Sounds Or Media Sounds And Mic** [manual] — It will enable system audio capture  
  deeplink: none
  1. Tap Sound.  
     _source: Open Settings, tap Advanced features, tap Screenshots and screen recordings, tap Screen recorder settings, tap Sound, and select Media sounds or Media sounds and mic_
  1. Select Media sounds or Media sounds and mic.  
     _source: Open Settings, tap Advanced features, tap Screenshots and screen recordings, tap Screen recorder settings, tap Sound, and select Media sounds or Media sounds and mic_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 2 | Screen-recorder audio flow is grounded; Screenshots and screen recordings deeplink opens the correct area (other link is placeholder). |

## S2-15: Face unlock works in a bright room but fails constantly at night with the lights off.

**Reference:** Face recognition fails in low light

### Face unlock fails (score 0.9)

- **Face Recognition** [auto] — It will improve face unlock in darkness  
  deeplink: Open the Face recognition settings page
  1. Open Settings.  
     _source: Open Settings, tap Security and privacy, tap Biometrics, tap Face recognition, and turn on Brighten screen_
  1. Tap Security and privacy.  
     _source: Open Settings, tap Security and privacy, tap Biometrics, tap Face recognition, and turn on Brighten screen_
  1. Tap Biometrics.  
     _source: Open Settings, tap Security and privacy, tap Biometrics, tap Face recognition, and turn on Brighten screen_
  1. Tap Face recognition.  
     _source: Open Settings, tap Security and privacy, tap Biometrics, tap Face recognition, and turn on Brighten screen_
  1. Turn on Brighten screen.  
     _source: Open Settings, tap Security and privacy, tap Biometrics, tap Face recognition, and turn on Brighten screen_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Face-recognition troubleshooting is grounded; link is a placeholder. |

## S2-16: The app drawer icons rearrange themselves every time I restart the phone.

**Reference:** App icons rearranging

### App icons rearranging (score 0.9)

- **Apps Screen** [manual] — It will reset icon layout order  
  deeplink: none
  1. Open the Apps screen.  
     _source: Open the Apps screen, tap the three-dot menu, tap Sort, and select Custom order_
  1. Tap the three-dot menu.  
     _source: Open the Apps screen, tap the three-dot menu, tap Sort, and select Custom order_
  1. Tap Sort.  
     _source: Open the Apps screen, tap the three-dot menu, tap Sort, and select Custom order_
  1. Select Custom order.  
     _source: Open the Apps screen, tap the three-dot menu, tap Sort, and select Custom order_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | App drawer guidance is grounded and manual. |

## S2-17: My phone's compass app always points about 30 degrees off from true north.

**Reference:** Compass inaccurate

### Compass inaccuracy (score 0.85)

- **Calibrate Compass** [manual] — It will improve compass accuracy  
  deeplink: none
  1. Move the phone in a figure-eight motion several times.  
     _source: Calibrate the compass by moving the phone in a figure-eight motion several times._
- **Remove Magnetic Interference** [manual] — It will eliminate external magnetic influence  
  deeplink: none
  1. Remove magnetic cases or mounts nearby.  
     _source: Remove magnetic cases or mounts nearby_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Compass calibration and magnetic-interference checks are grounded and manual. |

## S2-18: The dual SIM phone only shows signal bars for one card even though both are active.

**Reference:** Second SIM no signal

### Second SIM no (score 0.9)

- **SIM Manager** [auto] — It will ensure both SIMs are active  
  deeplink: Enable SIM manager
  1. Open Settings.  
     _source: Open Settings, tap Connections, tap SIM manager, and make sure both SIM cards are turned on._
  1. Tap Connections.  
     _source: Open Settings, tap Connections, tap SIM manager, and make sure both SIM cards are turned on._
  1. Tap SIM manager.  
     _source: Open Settings, tap Connections, tap SIM manager, and make sure both SIM cards are turned on._
  1. Turn on both SIM cards.  
     _source: Open Settings, tap Connections, tap SIM manager, and make sure both SIM cards are turned on._
- **SIM Reinsertion** [manual] — It will reseat the second SIM card  
  deeplink: none
  1. Remove the second SIM card.  
     _source: Then remove and reinsert the second SIM card_
  1. Reinsert the second SIM card.  
     _source: Then remove and reinsert the second SIM card_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 0 | Steps correctly use SIM manager and reseat SIM, but deeplink Enable SIM manager does not correspond to turning on both individual SIM cards. |

## S2-19: My phone's NFC won't tap-to-pay anymore since I added a new bank card.

**Reference:** NFC payments stopped working

### NFC payment issue (score 0.9)

- **Access NFC Settings** [auto] — It will open NFC and contactless payments  
  deeplink: Enable NFC and contactless payments
  1. Open Settings.  
     _source: Open Settings, tap Connections, tap NFC and contactless payments, turn on NFC, then tap Contactless payments and select your payment app as the default_
  1. Tap Connections.  
     _source: Open Settings, tap Connections, tap NFC and contactless payments, turn on NFC, then tap Contactless payments and select your payment app as the default_
  1. Tap NFC and contactless payments.  
     _source: Open Settings, tap Connections, tap NFC and contactless payments, turn on NFC, then tap Contactless payments and select your payment app as the default_
- **Select Payment App** [auto] — It will set default contactless payment app  
  deeplink: View Default wallet app
  1. Tap Contactless payments.  
     _source: Open Settings, tap Connections, tap NFC and contactless payments, turn on NFC, then tap Contactless payments and select your payment app as the default_
  1. Select your payment app as the default.  
     _source: Open Settings, tap Connections, tap NFC and contactless payments, turn on NFC, then tap Contactless payments and select your payment app as the default_
- **Enable NFC** [manual] — It will activate NFC functionality  
  deeplink: none
  1. Turn on NFC.  
     _source: Open Settings, tap Connections, tap NFC and contactless payments, turn on NFC, then tap Contactless payments and select your payment app as the default_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 1.5 | NFC/payment-app steps are grounded. NFC deeplink enables NFC rather than merely opening the requested screen (partial); Default wallet app deeplink is exact. |

## S2-20: The screen has a faint burn-in shadow of the navigation bar visible on white backgrounds.

**Reference:** Screen burn-in

### Screen burn-in (score 0.0)

- **Contact Service Center** [manual] — It will inspect or replace display  
  deeplink: none
  1. Contact an authorized service center.  
     _source: Contact an authorized service center to have the display inspected or replaced_
  1. Have the display inspected or replaced.  
     _source: Contact an authorized service center to have the display inspected or replaced_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Service-center recommendation matches the burn-in reference; no auto deeplink. |

## S3-21: My Bluetooth headphones keep disconnecting AND the camera app crashes every time I open it.

**Reference:** Bluetooth drops and camera crashes

### Bluetooth drops (score 0.9)

- **Bluetooth** [auto] — It will manage paired devices  
  deeplink: Open the Bluetooth settings page
  1. Open Settings.  
     _source: For Bluetooth drops, open Settings, tap Connections, tap Bluetooth, unpair the headphones, and pair them again._
  1. Tap Connections.  
     _source: For Bluetooth drops, open Settings, tap Connections, tap Bluetooth, unpair the headphones, and pair them again._
  1. Tap Bluetooth.  
     _source: For Bluetooth drops, open Settings, tap Connections, tap Bluetooth, unpair the headphones, and pair them again._
- **Unpair Headphones** [manual] — It will remove headphones from paired list  
  deeplink: none
  1. Unpair the headphones.  
     _source: For Bluetooth drops, open Settings, tap Connections, tap Bluetooth, unpair the headphones, and pair them again._
- **Pair Headphones** [manual] — It will re-establish the Bluetooth connection  
  deeplink: none
  1. Pair the headphones again.  
     _source: For Bluetooth drops, open Settings, tap Connections, tap Bluetooth, unpair the headphones, and pair them again._

### Camera crashes (score 0.85)

- **Camera** [auto] — It will open camera app settings  
  deeplink: View Camera access
  1. Open Settings.  
     _source: For Bluetooth drops, open Settings, tap Connections, tap Bluetooth, unpair the headphones, and pair them again._
  1. Tap Apps.  
     _source: Separately, for camera crashes, open Settings, tap Apps, tap Camera, tap Storage, and tap Clear cache_
  1. Tap Camera.  
     _source: Separately, for camera crashes, open Settings, tap Apps, tap Camera, tap Storage, and tap Clear cache_
- **Clear Cache** [manual] — It will remove temporary camera data  
  deeplink: none
  1. Tap Storage.  
     _source: Separately, for camera crashes, open Settings, tap Apps, tap Camera, tap Storage, and tap Clear cache_
  1. Tap Clear cache.  
     _source: Separately, for camera crashes, open Settings, tap Apps, tap Camera, tap Storage, and tap Clear cache_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 0 | Both issue plans are grounded. Bluetooth link is placeholder; Camera access deeplink is the wrong screen for the Apps > Camera > Storage/cache path. |

## S3-22: The keyboard switches language randomly AND my notifications are delayed by minutes.

**Reference:** Keyboard language and notification delays

### Keyboard language (score 0.9)

- **Languages And Types** [auto] — It will remove unused languages  
  deeplink: Open the Languages settings page
  1. Open Settings.  
     _source: Separately, for delayed notifications, open Settings, tap Apps, select the app, tap Battery, and choose Unrestricted_
  1. Tap General management.  
     _source: For language switching, open Settings, tap General management, tap Keyboard, tap Languages and types, and remove unused languages._
  1. Tap Keyboard.  
     _source: For language switching, open Settings, tap General management, tap Keyboard, tap Languages and types, and remove unused languages._
  1. Tap Languages and types.  
     _source: For language switching, open Settings, tap General management, tap Keyboard, tap Languages and types, and remove unused languages._
  1. Remove unused languages.  
     _source: For language switching, open Settings, tap General management, tap Keyboard, tap Languages and types, and remove unused languages._

### Notification delay (score 0.9)

- **Battery** [auto] — It will set unrestricted battery  
  deeplink: Open the Battery settings page
  1. Open Settings.  
     _source: Separately, for delayed notifications, open Settings, tap Apps, select the app, tap Battery, and choose Unrestricted_
  1. Tap Apps.  
     _source: Separately, for delayed notifications, open Settings, tap Apps, select the app, tap Battery, and choose Unrestricted_
  1. Select the app.  
     _source: Separately, for delayed notifications, open Settings, tap Apps, select the app, tap Battery, and choose Unrestricted_
  1. Tap Battery.  
     _source: Separately, for delayed notifications, open Settings, tap Apps, select the app, tap Battery, and choose Unrestricted_
  1. Choose Unrestricted.  
     _source: Separately, for delayed notifications, open Settings, tap Apps, select the app, tap Battery, and choose Unrestricted_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Both keyboard-language and delayed-notification plans are grounded; links are placeholders. |

## S3-23: Face unlock fails constantly at night AND the phone overheats during video calls.

**Reference:** Face unlock and overheating

### Face unlock fails (score 0.85)

- **Face Recognition** [auto] — It will brighten screen for face unlock  
  deeplink: Open the Face recognition settings page
  1. Open Settings.  
     _source: For face unlock at night, open Settings, tap Security and privacy, tap Biometrics, tap Face recognition, and turn on Brighten screen._
  1. Tap Security and privacy.  
     _source: For face unlock at night, open Settings, tap Security and privacy, tap Biometrics, tap Face recognition, and turn on Brighten screen._
  1. Tap Biometrics.  
     _source: For face unlock at night, open Settings, tap Security and privacy, tap Biometrics, tap Face recognition, and turn on Brighten screen._
  1. Tap Face recognition.  
     _source: For face unlock at night, open Settings, tap Security and privacy, tap Biometrics, tap Face recognition, and turn on Brighten screen._
  1. Turn on Brighten screen.  
     _source: For face unlock at night, open Settings, tap Security and privacy, tap Biometrics, tap Face recognition, and turn on Brighten screen._

### Phone overheats (score 0.8)

- **Power Saving** [auto] — It will limit power usage to prevent  
  deeplink: Enable Power saving
  1. Open Settings.  
     _source: For face unlock at night, open Settings, tap Security and privacy, tap Biometrics, tap Face recognition, and turn on Brighten screen._
  1. Tap Battery.  
     _source: Separately, for overheating on video calls, close background apps and open Settings, tap Battery, and turn on Power saving_
  1. Turn on Power saving.  
     _source: Separately, for overheating on video calls, close background apps and open Settings, tap Battery, and turn on Power saving_
- **Background Apps** [manual] — It will reduce load during video calls  
  deeplink: none
  1. Close background apps.  
     _source: Separately, for overheating on video calls, close background apps and open Settings, tap Battery, and turn on Power saving_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 2 | Both face-unlock and overheating plans are grounded; Power saving deeplink performs the intended action (face link is placeholder). |

## S3-24: Wi-Fi won't connect at my office AND the fingerprint sensor stopped working since the update.

**Reference:** Wi-Fi and fingerprint issues

### Wi-Fi connection (score 0.9)

- **Connections** [auto] — It will reset the Wi-Fi network  
  deeplink: Open the Wi-Fi settings page
  1. Open Settings.  
     _source: For office Wi-Fi, open Settings, tap Connections, tap Wi-Fi, forget the network, and rejoin it._
  1. Tap Connections.  
     _source: For office Wi-Fi, open Settings, tap Connections, tap Wi-Fi, forget the network, and rejoin it._
  1. Tap Wi-Fi.  
     _source: For office Wi-Fi, open Settings, tap Connections, tap Wi-Fi, forget the network, and rejoin it._
  1. Forget the network.  
     _source: For office Wi-Fi, open Settings, tap Connections, tap Wi-Fi, forget the network, and rejoin it._
  1. Rejoin the network.  
     _source: For office Wi-Fi, open Settings, tap Connections, tap Wi-Fi, forget the network, and rejoin it._

### Fingerprint sensor (score 0.9)

- **Security And Privacy** [auto] — It will re-register the fingerprint  
  deeplink: View Fingerprint unlock
  1. Open Settings.  
     _source: For office Wi-Fi, open Settings, tap Connections, tap Wi-Fi, forget the network, and rejoin it._
  1. Tap Security and privacy.  
     _source: Separately, for the fingerprint sensor, open Settings, tap Security and privacy, tap Biometrics, tap Fingerprints, and re-register your fingerprint_
  1. Tap Biometrics.  
     _source: Separately, for the fingerprint sensor, open Settings, tap Security and privacy, tap Biometrics, tap Fingerprints, and re-register your fingerprint_
  1. Tap Fingerprints.  
     _source: Separately, for the fingerprint sensor, open Settings, tap Security and privacy, tap Biometrics, tap Fingerprints, and re-register your fingerprint_
  1. Re-register your fingerprint.  
     _source: Separately, for the fingerprint sensor, open Settings, tap Security and privacy, tap Biometrics, tap Fingerprints, and re-register your fingerprint_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 1 | Both Wi-Fi and fingerprint plans are grounded. Wi-Fi link is placeholder; Fingerprint unlock is the right area but not the exact re-register action. |

## S4-25: Something feels off about my phone lately, it's just not working right.

**Reference:** General performance issues

### Phone performance (score 0.77)

- **Restart Phone** [critical] — It will refresh system operations  
  deeplink: none
  1. Press and hold the Power button.  
     **_no matching sentence in reference_**
  1. Tap Restart.  
     _source: Restart the phone and install the latest software update from Settings, Software update_
- **Software Update** [critical] — It will install latest improvements  
  deeplink: none
  1. Open Settings.  
     _source: Restart the phone and install the latest software update from Settings, Software update_
  1. Tap Software update.  
     _source: Restart the phone and install the latest software update from Settings, Software update_
  1. Tap Download and install.  
     _source: Restart the phone and install the latest software update from Settings, Software update_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Restart and software-update steps match the general-performance reference; unsupported Power-button step is harmless navigation. |

## S4-26: My phone screen is completely shattered and pieces of glass are falling off.

**Reference:** Cracked screen

### Shattered screen (score 0.9)

- **Back Up Data** [auto] — It will preserve your personal data  
  deeplink: Enable Back up data (TechCorp Cloud)
  1. Open Settings.  
     **_no matching sentence in reference_**
  1. Tap Accounts and backup.  
     _source: Back up your data if possible and visit an authorized service center to replace the display_
  1. Tap Backup and restore.  
     _source: Back up your data if possible and visit an authorized service center to replace the display_
  1. Tap Back up data.  
     _source: Back up your data if possible and visit an authorized service center to replace the display_
  1. Select data to back up.  
     _source: Back up your data if possible and visit an authorized service center to replace the display_
  1. Tap Back up.  
     _source: Back up your data if possible and visit an authorized service center to replace the display_
- **Visit Service Center** [manual] — It will replace the damaged display  
  deeplink: none
  1. Locate authorized service center.  
     _source: Back up your data if possible and visit an authorized service center to replace the display_
  1. Visit center with device.  
     _source: Back up your data if possible and visit an authorized service center to replace the display_
  1. Request screen replacement.  
     **_no matching sentence in reference_**

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 2 | Backup and service steps are directly implied by the cracked-screen reference; backup deeplink performs the intended backup-data action. |

## S4-27: I dropped my phone in a pool three days ago and now the speaker sounds crackly.

**Reference:** Water damage to speaker

### Speaker crackly (score 0.5)

- **Visit Service Center** [manual] — It will inspect for water damage  
  deeplink: none
  1. Locate authorized service center.  
     _source: Visit an authorized service center for inspection_
  1. Bring phone for inspection.  
     _source: Visit an authorized service center for inspection_
  1. Request speaker evaluation.  
     **_no matching sentence in reference_**

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Service-center inspection matches the water-damage reference; speaker evaluation is directly implied by inspection. |

## S4-28: My cat knocked my phone off the table and now the top-left corner of the screen doesn't respond to touch.

**Reference:** Touch not responding in one area

### Touch dead zone (score 0.68)

- **Remove Screen Protector** [manual] — It will eliminate interference from cover  
  deeplink: none
  1. Peel off the screen protector.  
     _source: Remove any screen protector, then visit an authorized service center if the area still does not respond_
  1. Clean the screen surface.  
     **_no matching sentence in reference_**
- **Visit Service Center** [manual] — It will diagnose digitizer damage  
  deeplink: none
  1. Locate an authorized service center.  
     _source: Remove any screen protector, then visit an authorized service center if the area still does not respond_
  1. Bring the device for inspection.  
     **_no matching sentence in reference_**

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Screen-protector removal followed by service inspection matches the reference; added cleaning/bring-device wording is harmless. |

## S4-29: asdkfj screen bad help pls

**Reference:** Screen problems

### Screen issue (score 0.8)

- **Check Display Settings** [auto] — It will adjust screen behavior  
  deeplink: Open the Display settings page
  1. Open Settings.  
     _source: If the screen still misbehaves, open Settings, tap Display, and check brightness and Motion smoothness_
  1. Tap Display.  
     _source: If the screen still misbehaves, open Settings, tap Display, and check brightness and Motion smoothness_
  1. Check brightness and Motion smoothness.  
     _source: If the screen still misbehaves, open Settings, tap Display, and check brightness and Motion smoothness_
- **Restart Phone** [critical] — It will refresh the system  
  deeplink: none
  1. Restart the phone.  
     _source: Restart the phone._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Display checks and restart are grounded; Display link is a dummy_positive placeholder. |

## S4-30: My phone works fine but my smart watch paired to it keeps losing connection.

**Reference:** Watch disconnecting

### Watch disconnecting (score 0.9)

- **Tap Watch Settings** [auto] — It will access watch configuration  
  deeplink: Open the Watch settings page
  1. Tap Watch settings.  
     _source: Open the Wearable app, tap Watch settings, and reset the connection._
- **Open Wearable App** [manual] — It will launch the wearable manager  
  deeplink: none
  1. Open Wearable app.  
     _source: Open the Wearable app, tap Watch settings, and reset the connection._
- **Reset The Connection** [manual] — It will reestablish Bluetooth link  
  deeplink: none
  1. Reset the connection.  
     _source: Open the Wearable app, tap Watch settings, and reset the connection._

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Watch settings, wearable app and connection reset are grounded; link is a placeholder. |

## S4-31: Can you make my phone charge faster than what the charger supports?

**Reference:** Fast charging

### Enable fast charging (score 0.9)

- **Tap More Battery Settings** [auto] — It will show advanced battery options  
  deeplink: Open the More battery settings page
  1. Open Settings.  
     _source: Open Settings, tap Battery, tap More battery settings, and turn on Fast charging_
  1. Tap Battery.  
     _source: Open Settings, tap Battery, tap More battery settings, and turn on Fast charging_
  1. Tap More battery settings.  
     _source: Open Settings, tap Battery, tap More battery settings, and turn on Fast charging_
- **Turn On Fast Charging** [manual] — It will enable faster charging speed  
  deeplink: none
  1. Turn on Fast charging.  
     _source: Open Settings, tap Battery, tap More battery settings, and turn on Fast charging_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Fast-charging navigation and toggle match the reference; link is a placeholder. |

## S4-32: The phone is possessed, it turns on by itself at 3am every night and plays music.

**Reference:** Phone turns on and plays sound at night

### Phone turns (score 0.9)

- **Auto Restart** [auto] — It will review scheduled restart times  
  deeplink: Open the Reset settings page
  1. Open Settings.  
     _source: Open Settings, tap General management, tap Reset, tap Auto restart, and review scheduled times._
  1. Tap General management.  
     _source: Open Settings, tap General management, tap Reset, tap Auto restart, and review scheduled times._
  1. Tap Reset.  
     _source: Open Settings, tap General management, tap Reset, tap Auto restart, and review scheduled times._
  1. Tap Auto restart.  
     _source: Open Settings, tap General management, tap Reset, tap Auto restart, and review scheduled times._
- **Clock App** [manual] — It will check alarms near 3 AM  
  deeplink: none
  1. Open Clock app.  
     _source: Check the Clock app for alarms set around 3 AM_
  1. Tap Alarm.  
     _source: Check the Clock app for alarms set around 3 AM_
  1. Review alarms near 3 AM.  
     **_no matching sentence in reference_**

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | n/a | Scheduled restart and 3 AM alarm checks match the reference; link is a placeholder. |

## S6-39: mera phone ka screen baar baar flicker kar raha hai

**Reference:** Screen flickering

### Screen flickering (score 0.9)

- **Motion Smoothness** [auto] — It will set refresh rate to standard  
  deeplink: Adjust Motion smoothness
  1. Open Settings.  
     _source: Open Settings, tap Display, tap Motion smoothness, and select Standard._
  1. Tap Display.  
     _source: Open Settings, tap Display, tap Motion smoothness, and select Standard._
  1. Tap Motion smoothness.  
     _source: Open Settings, tap Display, tap Motion smoothness, and select Standard._
  1. Select Standard.  
     _source: Open Settings, tap Display, tap Motion smoothness, and select Standard._
- **Restart Phone** [critical] — It will resolve persistent flicker  
  deeplink: none
  1. Restart the phone.  
     _source: Restart the phone if the flicker continues_

| Steps (0-3) | Deeplink (0-2) | Notes |
|---|---|---|
| 3 | 2 | Flicker troubleshooting is grounded; Motion smoothness deeplink opens/adjusts the exact target setting. |
