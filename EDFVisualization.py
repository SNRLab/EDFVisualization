'''
Future Work:
- Clean up the naming for all Slicer nodes
 - User can set size of fiducials
 - keep track of all nodes associated with each application, and add way to select which one should be active/inactive
 - Error if EDF file is valid but has no sensors or data?
 - Add in way to unselect specific sensors
 - Remove ScriptedLoadableModule class
 - If a fiducial list is loaded when a Sensor is arleady selected, the size mismatch message will display 0 for the size of the fiducial list
 - Allow them to name the sequence
 - FPS of the sequence should be based on duration of EDF reading

'''
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *

def format( num ):
  return '%.2f'%num

# 2's complement decoding
def decode( str ):
  num = ord( str[0] ) + (ord( str[1] )*256)
  return -(num & 32768) + (num & ~32768)
  
class EDFParser:
  def __init__(self, path):
    with open( path, 'rb' ) as f:
      self.data = f.read()
      self.size = len(self.data)
    
      # The current location of the parser within the file
      # Start at 252 to skip the unneeded parts of the header
      self.index = 252
  
  def parse( self ):    
    # A list of all individual signals, ordered and grouped by timestamp
    timestamps = []
    
    # A list of all different types of sensors in this file
    sensors = []
    
    # A tree used to determine which signals belong to the same sensor type
    sensorTree = {}
    
    # Get the number of signals in the file
    numSignals = self.int(4)
    
    # A template list to represent the value of each signal at a single timestamp
    # Filled with 0's to start
    timestampTemplate = [0] * numSignals
    
    # A list of all individual signals (and their attributes) in this file
    signals = [ {
        "currentTimestampIndex" : 0,
        "index" : i,
        "label" : self.read(16),
        "sensorTreeBranch" : sensorTree
      } for i in range(numSignals) ]
    
    for record in signals:
      record["type"] = self.readAndBranch(80, record)
      
    for record in signals:
      record["units"] = self.readAndBranch(8, record)
      
    for record in signals:
      record["sensorMin"] = self.floatAndBranch(8, record)
      
    for record in signals:
      record["sensorMax"] = self.floatAndBranch(8, record)
      
    for record in signals:
      record["digMin"] = self.intAndBranch(8, record)
      
    for record in signals:
      record["digMax"] = self.intAndBranch(8, record)
      
      sensorData = record["sensorTreeBranch"]
      
      # This is the lowest point along the sensorTree, where the sensor specific data will be stored
      # If the data has already been initialized, then just add this index to the list of indices
      if "indices" in sensorData:
        sensorData["indices"].append( record["index"] )
      # Otherwise, initialize the data and store it
      else:
        for key in ["type","units","sensorMax","sensorMin","digMax","digMin"]:
          sensorData[key] = record[key]
        sensorData["DtoAratio"] = ( record["sensorMax"] - record["sensorMin"] ) / ( record["digMax"] - record["digMin"] )
        sensorData["indices"] = [ record["index"] ]
        
        sensors.append(sensorData)
      
    #skip filtering information
    self.index += 80*numSignals
      
    for record in signals:
      # Get the amount of samples collected at once
      # This represents the number of consecutive values in the EDF file which correspond to this signal
      record["sampleSize"] = self.range(8)
      
    #skip filler
    self.index += 32*numSignals
    
    while self.index < self.size:
      for record in signals:
        sensorData = record["sensorTreeBranch"]
        
        for i in record["sampleSize"]:
          timestampIndex = record["currentTimestampIndex"]
          
          record["currentTimestampIndex"] += 1
          
          # If the timestampIndex doesnt exist yet, add it to the timestamps array
          if timestampIndex == len(timestamps):
            timestamps.append( timestampTemplate[:] )
          
          timestampArr = timestamps[timestampIndex]
          
          # Decode the next two bytes and convert it to the analog value
          analogValue = self.decode() * sensorData["DtoAratio"]
          
          # Store the true analog value
          timestampArr[ record["index"] ] = analogValue
          
          #Store max/min
          if not "dataMax" in sensorData or analogValue > sensorData["dataMax"]:
            sensorData["dataMax"] = analogValue
            
          if not "dataMin" in sensorData or analogValue < sensorData["dataMin"]:
            sensorData["dataMin"] = analogValue
    
    # Return the timestamps and the sensors (sorted by size)
    return timestamps, sorted( sensors, key = lambda x : len(x["indices"]) )

  # To read a value from the data
  def read( self, size ):
    self.index += size
    return self.data[ self.index-size : self.index ].strip()
    
  # To read a value and convert it to an int
  def int( self, size ):
    return int( self.read(size) )
  
  def range( self, size ):
    return range( self.int(size) )
  
  # To read a value from the data, and then traverse the corresponding "sensorTreeBranch" branch
  def readAndBranch( self, size, record ):
    val = self.read(size)
    
    if val in record["sensorTreeBranch"]:
      branch = record["sensorTreeBranch"][val]
    else:
      branch = record["sensorTreeBranch"][val] = {}
      
    record["sensorTreeBranch"] = branch
    return val
  
  # To read and branch and then return the value as a float
  def floatAndBranch( self, size, record ):
    return float( self.readAndBranch( size, record ) )
    
  # To read and branch and then return the value as an int
  def intAndBranch( self, size, record ):
    return int( self.readAndBranch( size, record ) )
    
  # To read two bytes and decode from 2's complement format
  def decode( self ):
    self.index += 2
    return decode( self.data[ self.index-2 : self.index ] )
  
# EDFVisualization
class EDFVisualization(ScriptedLoadableModule):
  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "EDF Visualization"
    self.parent.categories = ["Quantification"]
    self.parent.dependencies = []
    self.parent.contributors = ["Brian Ninni (BWH)"]
    self.parent.helpText = ""
    self.parent.acknowledgementText = ""

# EDFVisualizationWidget
class EDFVisualizationWidget(ScriptedLoadableModuleWidget):
  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Parameters Area
    parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    parametersCollapsibleButton.text = "Parameters"
    self.layout.addWidget(parametersCollapsibleButton)
    parametersFormLayout = qt.QFormLayout(parametersCollapsibleButton)

    # Filepath Button
    filepathLayout = qt.QGridLayout()
    self.filepathText = qt.QLineEdit("Select an EDF File...")
    self.filepathText.enabled = False
    filepathLayout.addWidget( self.filepathText, 0, 0 )
    filepathButton = qt.QPushButton("Load")
    filepathButton.toolTip = "Select an EDF File"
    filepathButton.connect('clicked(bool)', self.onFilepathSelect)
    filepathLayout.addWidget( filepathButton, 0, 4 )
    parametersFormLayout.addRow(filepathLayout)
    
    # EDF Sensors Layout
    self.sensorDropdown = qt.QComboBox()
    self.resetSensorDropdown()
    self.sensorDropdown.connect('currentIndexChanged(int)', self.onSensorDropdown)
    parametersFormLayout.addRow("Sensors to model:", self.sensorDropdown)
    
    # Downsample input
    self.downsampleInput = qt.QSpinBox()
    self.downsampleInput.enabled = False
    self.downsampleInput.setMinimum(1)
    self.downsampleInput.setValue(1)
    parametersFormLayout.addRow("Downsample Factor: ", self.downsampleInput)
    
    # Fiducial selector
    self.fiducialListSelector = slicer.qMRMLNodeComboBox()
    self.fiducialListSelector.nodeTypes = ["vtkMRMLMarkupsFiducialNode"]
    self.fiducialListSelector.selectNodeUponCreation = True
    self.fiducialListSelector.addEnabled = False
    self.fiducialListSelector.removeEnabled = False
    self.fiducialListSelector.noneEnabled = False
    self.fiducialListSelector.showHidden = False
    self.fiducialListSelector.showChildNodeTypes = False
    self.fiducialListSelector.setMRMLScene( slicer.mrmlScene )
    self.fiducialListSelector.setToolTip( "Pick the fiducial list" )
    self.fiducialListSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.checkReadyToApply)
    parametersFormLayout.addRow( "Fiducial List: ", self.fiducialListSelector )
    
    # Color Range Radio Buttons
    self.sensorLimitsRadio = qt.QRadioButton("Sensor Limits")
    self.sensorLimitsRadio.checked = True
    dataLimitsRadio = qt.QRadioButton("Data Limits")
    dataLimitsRadio.checked = False
    self.radioLayout = qt.QGridLayout()
    radioLabel = qt.QLabel("Color Range Based on:")
    self.radioLayout.addWidget( radioLabel, 0, 0)
    self.radioLayout.addWidget( self.sensorLimitsRadio, 0, 1 )
    self.radioLayout.addWidget( dataLimitsRadio, 0, 2 )
    parametersFormLayout.addRow( self.radioLayout )
    
    # Apply Button
    self.applyButton = qt.QPushButton("Apply")
    self.applyButton.toolTip = "Run the sequence"
    self.applyButton.enabled = False
    self.applyButton.connect('clicked(bool)', self.onApplyButton)
    parametersFormLayout.addRow(self.applyButton)
    
    # Status Message
    self.statusMessageType = qt.QLabel()
    self.statusMessage = qt.QLabel()
    statusLayout = qt.QGridLayout()
    statusLayout.addWidget( self.statusMessageType, 0, 0, 1, 1 )
    statusLayout.addWidget( self.statusMessage, 0, 1, 1, 3)
    parametersFormLayout.addRow(statusLayout)

    # Add vertical spacer
    self.layout.addStretch(1)

    self.counters = {}
    self.filepath = None
    self.filename = None
    self.signals = None
    self.sensors = None
    self.prevDir = None

    try:
      slicer.vtkMRMLSequenceBrowserNode()
      slicer.vtkMRMLSequenceNode()
    except:
      filepathButton.enabled = False
      self.fiducialListSelector.enabled = False
      self.downsampleInput.enabled = False
      self.sensorLimitsRadio.enabled = False
      dataLimitsRadio.enabled = False
      self.displayError("The Sequences extension is not installed")
    
  def displayWarning( self, msg ):
    self.statusMessageType.setText("Warning:")
    self.statusMessageType.setStyleSheet("color:yellow")
    self.statusMessage.setText(msg)

  def displayError( self, msg ):
    self.statusMessageType.setText("Error:")
    self.statusMessageType.setStyleSheet("color:red")
    self.statusMessage.setText(msg)
    
  def displaySuccess( self, msg ):
    self.statusMessageType.setText("Success:")
    self.statusMessageType.setStyleSheet("color:green")
    self.statusMessage.setText(msg)
    
  def clearMessage( self ):
    self.statusMessageType.setText("")
    self.statusMessage.setText("")
    
  def resetFileData(self):
    self.filepath = None
    self.filename = None
    self.signals = None
    self.sensors = None
      
    self.downsampleInput.enabled = False
    self.downsampleInput.setValue(1)
      
    # Need to disable to ensure the "changed" event doesnt fire
    self.sensorDropdown.enabled = False
    self.clearSensorDropdown()
    self.resetSensorDropdown()
    
    self.filepathText.setText("Select an EDF File...")
    
  def resetSensorDropdown(self):
    self.sensorDropdown.addItem("Load EDF File first...")
    self.sensorDropdown.enabled = False
  
  def clearSensorDropdown(self):
    while self.sensorDropdown.count:
      self.sensorDropdown.removeItem(0)
    
  def buildSensorDropdown( self ):
    self.clearSensorDropdown()
    notfoundMatch = True
    difference = 0
    fiducialList = self.fiducialListSelector.currentNode()
    for i in range( len(self.sensors) ):
      sensor = self.sensors[i]
      type = sensor["type"]
      if not type:
        type = '<untyped>'
      name = type + '  |  Range ' + format(sensor["sensorMin"]) + " / " + format(sensor["sensorMax"]) + " " + sensor["units"]
      name += "  |  " + str(len( sensor["indices"] )) + " Sensor(s)  |  Min / Max " + format(sensor["dataMin"]) + " / " + format(sensor["dataMax"])
      self.sensorDropdown.addItem( name )
      if fiducialList and notfoundMatch:
        thisDiff = fiducialList.GetNumberOfFiducials() - len( sensor["indices"] )
        if thisDiff == 0:
          self.sensorDropdown.currentIndex = i
          notfoundMatch = False
        # if not exact match, then use if it is closest
        elif not difference or difference > abs(thisDiff):
          difference = abs(thisDiff)
          self.sensorDropdown.currentIndex = i
    self.sensorDropdown.enabled = True
    
  def onSensorDropdown(self):
    if self.sensorDropdown.enabled and self.sensorDropdown.count and self.fiducialListSelector.currentNode():
      self.displayFiducialLengthMismatchWarning()
    
  def onFilepathSelect(self):
    filepath = qt.QFileDialog.getOpenFileName(None, 'Open EDF File', self.prevDir, "*.edf")
    
    # Nothing chosen
    if filepath == '':
      self.displayWarning("No EDF File was selected")
      self.resetFileData()
      return
    
    # dont do anything if same file is chosen
    if filepath == self.filepath:
      self.clearMessage()
      return
    
    splitFilepath = filepath.split('/')
    
    filename = splitFilepath[-1].split('.')
    
    #Remember the directory
    self.prevDir = '/'.join( splitFilepath[:-1] )
    
    if filename[-1] == "edf":
      try:
        # TODO - if this line part fails, then it is an invalid filepath
        edf = EDFParser( filepath )
        self.signals, self.sensors = edf.parse()
        self.buildSensorDropdown()
        self.filepath = filepath
        self.filename = '.'.join( filename[:-1] )
        self.filepathText.setText( filepath )
        self.downsampleInput.enabled = True
        self.downsampleInput.setMaximum( len(self.signals) )
        # Set the default value so it will produce 250 samples
        self.downsampleInput.setValue( len(self.signals) / 250 )
        self.clearMessage()
      except:
        self.displayError("Unable to parse EDF file")
        self.resetFileData()
    else:
      self.displayWarning("Selected file is not an EDF file")
      self.resetFileData()
    
    # Update the Apply button
    self.checkReadyToApply()
    
  def checkReadyToApply(self):
    if self.fiducialListSelector.currentNode() and self.filepath:
      self.applyButton.enabled = True
      self.displayFiducialLengthMismatchWarning()
          
  def displayFiducialLengthMismatchWarning(self):
    fiducialListSize = self.fiducialListSelector.currentNode().GetNumberOfFiducials()
    sensorListSize = len( self.sensors[ self.sensorDropdown.currentIndex ]["indices"] )
    
    if fiducialListSize == sensorListSize:
      self.clearMessage()
    else:
      sizeToUse = min( fiducialListSize, sensorListSize )
      self.displayWarning("Fiducial count (" + str(fiducialListSize) + ") doesn't match Sensor count (" + str(sensorListSize) + "). Will only use the first " + str(sizeToUse) )
    
  def onApplyButton(self):
    if self.filepath in self.counters:
      counter = self.counters[self.filepath]
    else:
      counter = self.counters[self.filepath] = 1
	  
    logic = EDFVisualizationLogic()
    logic.run( self.fiducialListSelector.currentNode(), self.filepath, self.filename, self.downsampleInput.value, self.signals, self.sensors[ self.sensorDropdown.currentIndex ], self.sensorLimitsRadio.checked, str(counter) )
    self.displaySuccess("Generated Sequence '" + self.filename + " (" + str(counter) + ")'")
    
    self.counters[self.filepath] += 1
      
#
# EDFVisualizationLogic
#

class EDFVisualizationLogic(ScriptedLoadableModuleLogic):

  def run( self, list, filepath, filename, downsample, signals, sensor, useSensorLimits, index ):
    self.filename = filename
    self.index = index
    browser = slicer.vtkMRMLSequenceBrowserNode()
    browser.SetName( filename + ' (' + index + ')')
    slicer.mrmlScene.AddNode(browser)

    if useSensorLimits:
      colorMap = self.createColorMap( sensor["sensorMin"], sensor["sensorMax"] )
    else:
      colorMap = self.createColorMap( sensor["dataMin"], sensor["dataMax"] )

    num_of_fiducials = min( list.GetNumberOfFiducials(), len( sensor["indices"] ) )
    counter = 0

    points = vtk.vtkPoints()
	
    #Get the first row data
    colors = self.getRowAsArray( signals, sensor, counter, num_of_fiducials)

    arr = [0,0,0]

    for i in range(0,num_of_fiducials):
      list.GetNthFiducialPosition(i,arr)
      points.InsertNextPoint(arr[0], arr[1], arr[2])
    
    self.polydata = vtk.vtkPolyData()
    self.polydata.SetPoints(points)
    self.polydata.GetPointData().SetScalars(colors)

    sphereSource = vtk.vtkSphereSource()
    sphereSource.SetRadius(3)

    self.glyph3D = vtk.vtkGlyph3D()
    self.glyph3D.SetColorModeToColorByScalar()
    self.glyph3D.SetSourceConnection( sphereSource.GetOutputPort() )
    self.glyph3D.SetInputData(self.polydata)
    self.glyph3D.ScalingOff()
    self.glyph3D.Update()

    self.display = slicer.vtkMRMLModelDisplayNode()
    self.display.SetScalarVisibility(1)
    self.display.SetActiveScalarName("EDF Magnitude")
    self.display.SetName("EDF Magnitude (" + index + ")")
    slicer.mrmlScene.AddNode(self.display)

    model = slicer.vtkMRMLModelNode()
    model.SetName("EDF Magnitude (" + index + ")")
    slicer.mrmlScene.AddNode(model)

    model.SetAndObservePolyData(self.glyph3D.GetOutput())
    model.SetAndObserveDisplayNodeID( self.display.GetID() )
    self.display.SetScalarRangeFlag(0)
    self.display.SetAndObserveColorNodeID( colorMap.GetID() )
    
    #Add the Sequence Nodes
    self.addSequence( browser, model, "Model (" + index + ")" )
    self.addSequence( browser, self.display, "ModelDisplay (" + index + ")" )

    # Get the remaining rows
    while counter < len(signals):
      counter += 1
      if counter % downsample != 0:
        continue
      model.SetAndObservePolyData(self.glyph3D.GetOutput())
      newArr = self.getRowAsArray(signals, sensor, counter, num_of_fiducials )
      self.polydata.GetPointData().AddArray(newArr)
      self.glyph3D.Modified()
      self.glyph3D.Update()
      self.display.SetActiveScalarName( "EDF Magnitude " + str(counter) )
      browser.SaveProxyNodesState() #update the sequence

    return True
  
  def createColorMap( self, vMin, vMax ):
    ctf = vtk.vtkColorTransferFunction()
    ctf.AddRGBPoint( vMin,       0, 0,   0)
    ctf.AddRGBPoint( vMin * 0.9, 1, 0,   0)
    ctf.AddRGBPoint( vMin * 0.7, 1, 0.5, 0)
    ctf.AddRGBPoint( vMin * 0.4, 1, 1,   0)
    ctf.AddRGBPoint( 0,          1, 1,   1)
    ctf.AddRGBPoint( vMax * 0.4, 1, 1,   0)
    ctf.AddRGBPoint( vMax * 0.7, 1, 0.5, 0)
    ctf.AddRGBPoint( vMax * 0.9, 1, 0,   0)
    ctf.AddRGBPoint( vMax,       0, 0,   0)
    
    colorMap = slicer.vtkMRMLProceduralColorNode()
    colorMap.SetName( self.filename + ' (' + self.index + ')' )
    colorMap.SetAndObserveColorTransferFunction(ctf)
    slicer.mrmlScene.AddNode(colorMap)

    return colorMap
  
  def addSequence( self, browser, node, name ):
    seq = slicer.vtkMRMLSequenceNode()
    seq.SetName( name )
    slicer.mrmlScene.AddNode(seq)
    browser.AddSynchronizedSequenceNodeID(seq.GetID())
    browser.AddProxyNode( node, seq, False)
    browser.SetRecording( seq, 1 )
  
  def getRowAsArray( self, signals, sensor, counter, num_of_fiducials ):
    newArr = vtk.vtkFloatArray()
    newArr.SetName("EDF Magnitude " + str(counter) )
    for i in range(num_of_fiducials):
      index = sensor["indices"][i]
      newArr.InsertNextValue( signals[counter][index] )
    return newArr