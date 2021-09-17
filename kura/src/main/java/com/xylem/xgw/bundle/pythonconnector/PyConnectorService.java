package com.xylem.xgw.bundle.pythonconnector;

import java.util.Date;
import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Map.Entry;

import org.eclipse.kura.cloudconnection.listener.CloudConnectionListener;
import org.eclipse.kura.cloudconnection.listener.CloudDeliveryListener;
import org.eclipse.kura.cloudconnection.message.KuraMessage;
import org.eclipse.kura.cloudconnection.publisher.CloudPublisher;
import org.eclipse.kura.configuration.ConfigurableComponent;
import org.eclipse.kura.message.KuraPayload;
import org.osgi.service.component.ComponentContext;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class PyConnectorService implements ConfigurableComponent, CloudConnectionListener, CloudDeliveryListener {

	private static final Logger kuraLogger = LoggerFactory.getLogger(PyConnectorService.class);

	private static final String APP_ID = "com.xylem.xgw.bundle.pythonconnector.PyConnectorService";
	private static final String CONFIG_PYTHON_INTERPRETER = "python_interpreter";
	private static final String CONFIG_PY_FILE = "py_file";
	private static final String CONFIG_GET_INTERVAL = "get_interval";
	private static final String CONFIG_PARAMETERS = "parameters";
	private static final String ALL_CONFIGS[] = {CONFIG_PYTHON_INTERPRETER, CONFIG_PY_FILE, CONFIG_GET_INTERVAL, CONFIG_PARAMETERS};
	
	private Map<String, Object> properties;
	private CloudPublisher cloudPublisher;
	private PyInvoker pyInvoker;

	private MyReceiver receiver;

	private class MyReceiver implements PyInvoker.DataReceiver
	{

		@Override
		public void onMessage(String deviceName, String messageType, Map<String, Object> data) {
			kuraLogger.debug("New {} message from device {}: {}", messageType, deviceName, data);
			publish(deviceName, messageType, data);			
		}
		
	}
	
	public PyConnectorService() {
		receiver = new MyReceiver();
	}


	protected void activate(ComponentContext componentContext, Map<String, Object> properties) {
		kuraLogger.info("Activating bundle " + APP_ID + ".");
		updateAndRestart(properties, true);
	}

	protected void deactivate(ComponentContext componentContext) {
		kuraLogger.info("Deactivating bundle " + APP_ID + ".");
		if(pyInvoker != null)
			pyInvoker.stop();
		pyInvoker = null;
	}

	public void update(Map<String, Object> properties) {
		kuraLogger.info("Updating bundle " + APP_ID + ".");
		updateAndRestart(properties, false);
	}

	
	/**
	 * Called after a new set of properties has been configured on the service
	 */
	private void updateAndRestart(Map<String, Object> properties, boolean force) {
		if(this.properties != null && this.properties.equals(properties) && !force)
		{
			kuraLogger.info("No parameter update/restart required.");
			return;
		}
		
		this.properties = properties;
		List<String> entryStrings = new LinkedList<String>();
		if (properties != null && !properties.isEmpty()) {
			for(Entry<String, Object> entry : properties.entrySet()) {
				entryStrings.add(entry.getKey() + "=" + entry.getValue());				
			}
		}

		kuraLogger.info("(Re)start with parameters: "+String.join(",", entryStrings));
		
		
		for(String configItem : ALL_CONFIGS)
		{
			if (!this.properties.containsKey(configItem)) {
				kuraLogger.info("Update bundle " + APP_ID + " - Ignore as properties do not contain "+configItem+".");
				return;
			}
		}

		if(pyInvoker != null)
		{
			pyInvoker.stop();
			//FIXME: This may take a long time. Should we wait or do we need a method that requests a stop and then abandons?
			//Perhaps good to wait, so new instance only comes on when old instance has released resources.
			//It may be required to delegate starting and stopping to a worker thread so as not to block 
		}
		
		String interpreter = (String) properties.get(CONFIG_PYTHON_INTERPRETER);
		String pyFile = (String) properties.get(CONFIG_PY_FILE);
		Float getInterval = (Float)properties.get(CONFIG_GET_INTERVAL);
		String parameters = (String) properties.get(CONFIG_PARAMETERS);
		
		pyInvoker = new PyInvoker(receiver, interpreter, pyFile, parameters);
		try {
			pyInvoker.start(getInterval);
		} catch (Exception e) {
			// TODO Not sure whether there is a good way to handle this here. It's already been logged.
			;
		}
				
	}
	
	@Override
	public void onMessageConfirmed(String messageId) {
		// TODO Auto-generated method stub
		
	}

	@Override
	public void onDisconnected() {
		// TODO Auto-generated method stub
		
	}

	@Override
	public void onConnectionLost() {
		// TODO Auto-generated method stub
		
	}

	@Override
	public void onConnectionEstablished() {
		// TODO Auto-generated method stub
		
	}
	
	public void setCloudPublisher(CloudPublisher cloudPublisher) {
		this.cloudPublisher = cloudPublisher;
		this.cloudPublisher.registerCloudConnectionListener(PyConnectorService.this);
		this.cloudPublisher.registerCloudDeliveryListener(PyConnectorService.this);
	}

	public void unsetCloudPublisher(CloudPublisher cloudPublisher) {
		this.cloudPublisher.unregisterCloudConnectionListener(PyConnectorService.this);
		this.cloudPublisher.unregisterCloudDeliveryListener(PyConnectorService.this);
		this.cloudPublisher = null;
	}
	
	private void publish(String deviceName, String messageType, Map<String, Object> topicsAndValues) {
		if (this.cloudPublisher == null) {
			kuraLogger.warn("No cloud publisher selected. Cannot publish!");
			return;
		}

		// Allocate a new payload
		KuraPayload payload = new KuraPayload();

		// Timestamp the message
		payload.setTimestamp(new Date());

		// Add metrics
		topicsAndValues.forEach((topic, value) -> payload.addMetric(topic, value));

		// Assign message type property
		Map<String, Object> properties = new HashMap<String, Object>();
		String messageTypeOut;
		switch(messageType)
		{
		case "DATA":
			messageTypeOut = "data";
			break;
		case "STATUS":
			messageTypeOut = "status";
			break;
		default:
			messageTypeOut = "dump";			
		}
		properties.put("messageType", messageTypeOut);
		properties.put("assetName", deviceName);

		KuraMessage message = new KuraMessage(payload, properties);

		// Publish the message
		try {
			this.cloudPublisher.publish(message);
			kuraLogger.info("Published message with metrics: {}", payload.metricNames());
		} catch (Exception e) {
			kuraLogger.error("Cannot publish message with metrics: {}", payload.metricNames());
		}

	}

}
