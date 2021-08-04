package com.xylem.xgw.bundle.pythonconnector;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Reader;
import java.io.Writer;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;


public class PyInvoker {
	
	public interface DataReceiver {
		public void onData(Map<String, Object> data);
	}
	
	private static final Logger kuraLogger = LoggerFactory.getLogger(PyInvoker.class);

	//private final ExecutorService worker;
	private Process process;
	private Writer toPython;
	private BufferedReader fromPython;
	
	private Receiver receiver;
	private Thread receiverThread;
	private Supervisor supervisor;
	private Thread supervisorThread;
	private ScheduledExecutorService triggererES;
	private float getIntervalS;
	
	private boolean error;

	private DataReceiver dataReceiver;
	private String interpreter;
	private String pyFileName;
	private String parameterString;
	private int get_counter;
	private long pyLastModifiedTime;



	public PyInvoker(DataReceiver dataReceiver, String interpreter, String pyFileName, String parameterString) {
		process = null;
		this.interpreter = interpreter;
		this.pyFileName = pyFileName;
		this.dataReceiver = dataReceiver;
		this.parameterString = parameterString;
		this.supervisor = new Supervisor();
		error = false;
	}
	
	public void start(float getIntervalS)
	{
		this.getIntervalS = getIntervalS;
		this.get_counter = 0;
		if(supervisorThread != null || supervisor.isRunning())
		{
			kuraLogger.warn("Already running.");
			return;
		}
		supervisorThread = new Thread(supervisor);
		supervisorThread.start();
		
	}
		
	public void stop()
	{
		supervisor.stop();
		try {
			supervisorThread.join();
		} catch (InterruptedException e) {
			;
		}
		supervisorThread = null;
	}
	
	private class Supervisor implements Runnable
	{

		private boolean stopRequested;
		
		public boolean isRunning()
		{
			return process != null;
		}
		
		public void run()
		{
			boolean autoRestart;
			
			do
			{
				this.stopRequested = false;
				autoRestart = false;
				
				synchronized(this)
				{
				
					if(process != null)
					{
						kuraLogger.error("Cannot start python - already running");
						return;
					}
								
					kuraLogger.info("Invoking python");
					savePyFileModifiedDate();
					ProcessBuilder pb = new ProcessBuilder(interpreter, pyFileName);		
					try {
						process = pb.start();
					} catch (IOException e) {
						kuraLogger.error("Python interpreter or python script not found.");
						//FIXME: Report to cloud
						return;
					}	
				}
				
				toPython = new OutputStreamWriter(process.getOutputStream());
				fromPython = new BufferedReader(new InputStreamReader(process.getInputStream()));
				
				error = false;
				
				receiver = new Receiver();
				receiverThread = new Thread(receiver);
				receiverThread.start();
				
				cmdStart();
	
				triggererES = Executors.newSingleThreadScheduledExecutor();
				triggererES.scheduleAtFixedRate(PyInvoker.this::cmdGet, 0, (long)(getIntervalS*1000), TimeUnit.MILLISECONDS);
				
				while(!error && !this.stopRequested)
				{
					try {
						if(wasPyFileUpdated())
						{
							autoRestart = true;
							break;
						}
						Thread.sleep(1000);
					} catch (InterruptedException e) {
						;
					}
				}
				if(error)
				{
					kuraLogger.error("An error occured. Stopping.");
				}
				doStop(error);
				
				//FIXME: Hang around here and check for updates. Restart, if updated.
			}
			while(autoRestart);
		}

		public void stop()
		{
			this.stopRequested = true;
			supervisorThread.interrupt(); //TODO: I wonder whether this is a bit dirty
		}
		
		public void doStop(boolean onError)
		{
			
			if(process == null)
			{
				return;
			}
			triggererES.shutdown();
			try {
				boolean triggererShutdown = triggererES.awaitTermination(1, TimeUnit.SECONDS);
				if(!triggererShutdown)
				{
					kuraLogger.warn("Triggerer service did not shut down.");
				}
			} catch (InterruptedException e) {
				//Not planning to interrupt this thread
				;
			}
			
			if(!onError)
			{
				cmdStop();
			}
			
			receiver.stop();
			
			try {
				boolean terminated = process.waitFor(10, TimeUnit.SECONDS);
				if(!terminated)
				{
					kuraLogger.warn("Python process did not exit by itself. Terminating.");
					process.destroy();
					terminated = process.waitFor(10, TimeUnit.SECONDS);
				}
				if(!terminated)
				{
					kuraLogger.warn("Python process did not terminate. Killing.");
					process.destroyForcibly();
					terminated = process.waitFor(10, TimeUnit.SECONDS);
				}
				int rc = process.exitValue();
				if(rc == 0)
				{
					kuraLogger.info("The python process exited normally.");
				}
				else
				{
					kuraLogger.warn("The python process exited with error code {}.", rc);
					
				}
			} catch (InterruptedException e) {
				//Not planning to interrupt this thread
				;
			}
			
			process = null;
			triggererES = null;
			receiver = null;
			kuraLogger.info("Python stopped.");
		}
		
	}
	
	
	private class Receiver implements Runnable
	{
		private boolean stopRequested;
		
		public void stop()
		{
			this.stopRequested = true;
		}
		
		public void run()
		{
			while(!stopRequested)
			{
				try {
					String line;
					line = fromPython.readLine();
					if(line == null)
					{
						//End of stream
						break;
					}
					String[] parts = line.split("\t", 2);
					if(parts.length == 2 && parts[0].equals("DATA"))
					{
						Map<String, Object> args = parseArgs(parts[1]);
						if(!args.isEmpty())
						{
							dataReceiver.onData(args);
						}
					}
					else
					{
						kuraLogger.warn("Unknown message received from python: {}", line);
					}
				} catch (IOException e) {
					kuraLogger.error("Error reading from python");
					error = true;
					return;
				}
			}
		}
	}
	
	private void cmd(String command)
	{
		try {
			toPython.write(command+"\n");
			toPython.flush();	
		} catch (IOException e) {
			//Probably because process died.
			kuraLogger.error("Error sending command to python");
			error = true;
		}
	}
	
	private void cmdStart()
	{
		cmd(String.format("START\tGETINT=%f\tPARAMS=\"%s\"", this.getIntervalS, escapeString(this.parameterString)));
	}
	
	private void cmdStop()
	{
		cmd("STOP");
	}
	
	private void cmdGet()
	{
		cmd(String.format("GET\tCOUNT=%d", this.get_counter));
		this.get_counter++;
	}
	
	private void savePyFileModifiedDate()
	{
		File pyFile = new File(pyFileName);
		pyLastModifiedTime = pyFile.lastModified();
	}
	
	private boolean wasPyFileUpdated() {
		File pyFile = new File(pyFileName);
		long latestPyLastModified = pyFile.lastModified();
		return latestPyLastModified > pyLastModifiedTime; //Also works, if file no longer exists, as 0L is returned in that case.
	}
	
	public static String escapeString(String s) {
		  return s.replace("\\", "\\\\")
		          .replace("\t", "\\t")
		          .replace("\b", "\\b")
		          .replace("\n", "\\n")
		          .replace("\r", "\\r")
		          .replace("\f", "\\f")
		          .replace("\'", "\\'")
		          .replace("\"", "\\\"");
	}
	
	public static String unEscapeString(String s){
		  return s.replace("\\\"", "\"")
				  .replace("\\'", "\'")
		          .replace("\\t", "\t")
		          .replace("\\b", "\b")
		          .replace("\\n", "\n")
		          .replace("\\r", "\r")
		          .replace("\\f", "\f")
		          .replace("\\\\", "\\");
	}
	
	public static Map<String, Object> parseArgs(String argString)
	{
		String [] entries = argString.split("\t");
		Map<String, Object> paramsAndValues = new HashMap<String, Object>();
		for(String entry: entries)
		{
			String [] leftRight = entry.split("=", 2);
			if(leftRight.length != 2)
			{
				continue;
			}
			String left = leftRight[0];
			String right = leftRight[1];
			if(right.isEmpty())
			{
				continue;
			}
			Object value;
			if(right.startsWith("\"") && right.endsWith("\""))
			{
				value = unEscapeString(right.substring(1, right.length()-1));
			}
			else
			{
				try
				{
					value = Integer.valueOf(right);
				}
				catch(NumberFormatException e1)
				{
					try
					{
						value = Double.valueOf(right);
					}
					catch(NumberFormatException e2)
					{
						continue;
					}
				}
			}
			paramsAndValues.put(left, value);
		}
		return paramsAndValues;
	}

}
