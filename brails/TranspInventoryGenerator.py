# -*- coding: utf-8 -*-
#
# Copyright (c) 2023 The Regents of the University of California
#
# This file is part of BRAILS.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# You should have received a copy of the BSD 3-Clause License along with
# BRAILS. If not, see <http://www.opensource.org/licenses/>.
#
# Contributors:
# Barbaros Cetiner
# Frank McKenna
# Jinyan Zhao

#
# Last updated:
# 08-29-2023 

from brails.workflow.TransportationElementHandler import TransportationElementHandler
import geopandas as gpd
import pandas as pd
import momepy
from shapely.geometry import MultiLineString
import shapely
import gc
import json
import warnings
import numpy as np

# The map defines the default values according to MTFCC code
# https://www2.census.gov/geo/pdfs/maps-data/data/tiger/tgrshp2009/TGRSHP09AF.pdf
# May need better models
ROADTYPE_MAP = {'S1100':"primary", "S1200":"secondary", "S1400":"residential",
                "S1500":"unclassified", "S1630":"unclassified", "S1640":"unclassified",
                "S1710":"unclassified", "S1720":"unclassified", "S1730":"unclassified",
                "S1740":"unclassified", "S1750":"unclassified", "S1780":"unclassified",
                "S1810":"unclassified", "S1820":"unclassified", "S1830":"unclassified"}
ROADLANES_MAP = {'S1100':4, "S1200":2, "S1400":1, "S1500":1, "S1630":1, "S1640":1, 
                 "S1710":1, "S1720":1, "S1730":1, "S1740":1, "S1750":1, "S1780":1,
                 "S1810":1, "S1820":1, "S1830":1}
        # speedMap = {'S1100':70,"S1200":55,"S1400":25,"S1500":25,"S1630":25,"S1640":25,"S1710":25,"S1720":25,"S1730":25}
ROADCAPACITY_MAP = {'S1100':70, "S1200":55, "S1400":25, "S1500":25, "S1630":25, "S1640":25,
                    "S1710":25, "S1720":25, "S1730":25, "S1740":10, "S1750":10, "S1780":10,
                    "S1810":10, "S1820":10, "S1830":10}


class TranspInventoryGenerator:

    def __init__(self, location='Berkeley, CA'):                
        self.enabledElements = ['roads','bridges','tunnels','railroads']
        self.location = location
        self.workDir = 'tmp'
        self.modelDir = 'tmp/models'
        self.inventory_files = ''
    
    def enabled_elements(self):
        print('Here is the list of attributes currently enabled in InventoryGenerator:\n')
        for element in self.enabledElements:
            print(f'       {element}')

    def generate(self):
        tphandler = TransportationElementHandler()
        tphandler.fetch_transportation_elements(self.location) 
        
        self.inventory_files = tphandler.output_files
        
        outfiles = ", ".join(value for value in tphandler.output_files.values())
        print(f'\nTransportation inventory data available in {outfiles}')
    
    def combineAndFormat_HWY(self, minimumHAZUS, connectivity, maxRoadLength):
        print(f"Formatting and combining fetched data in {self.inventory_files}")
        # Format bridges
        bridgesFile = self.inventory_files.get("bridges", None)
        if bridgesFile is not None:
            bridges_gdf = gpd.read_file(bridgesFile)
            bnodeDF, bridgesDict = formatBridges(minimumHAZUS, connectivity, bridges_gdf)
        else:
            bnodeDF = gpd.GeoDataFrame(columns = ["nodeID", "geometry"], crs = "epsg:4326")
            bridgesDict = {'type':'FeatureCollection', 
                       "crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" } },
                       'features':[]}

        # Format roadways
        roadsFile = self.inventory_files.get("roads", None)
        if roadsFile is not None:
            roads_gdf = gpd.read_file(roadsFile).explode(index_parts = False)
            rnodeDF, roadsDict = formatRoads(minimumHAZUS, connectivity,\
                                             maxRoadLength, roads_gdf)
        else:
            rnodeDF = gpd.GeoDataFrame(columns = ["nodeID", "geometry"], crs = "epsg:4326")
            roadsDict = {'type':'FeatureCollection', 
                       "crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" } },
                       'features':[]}
        
        # Format tunnels
        tunnelsFile = self.inventory_files.get("tunnels", None)
        if tunnelsFile is not None:
            tunnels_gdf = gpd.read_file(tunnelsFile).explode(index_parts = False)
            tnodeDF, tunnelsDict = formatTunnels(minimumHAZUS, connectivity, tunnels_gdf)
        else:
            tnodeDF = gpd.GeoDataFrame(columns = ["nodeID", "geometry"], crs = "epsg:4326")
            tunnelsDict = {'type':'FeatureCollection', 
                       "crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" } },
                       'features':[]}

        # Combine nodes and update dicts
        combinedGeoJSON = combineDict(bnodeDF, bridgesDict, rnodeDF, roadsDict,\
                                      tnodeDF, tunnelsDict, connectivity)
        # Dump to json file
        with open("hwy_inventory.json", "w") as f:
            json.dump(combinedGeoJSON, f, indent = 2)
        
        # # Combine the geoJSON files into a single geoJSON
        # combinedFileName = 'hwy_inventory.geojson'
        # combineGeoJSON(bridgesFile, tunnelsFile, roadsFile, combinedFileName)
        
        return
        
# Break down long roads according to delta
def breakDownLongEdges(edges, delta, tolerance = 10e-3):
    dropedEdges = []
    newEdges = []
    crs = edges.crs
    edgesOrig = edges.copy()
    # edgesOrig["IDbase"] = edgesOrig["OID"].apply(lambda x: x.split('_')[0])
    edgesOrig["IDbase"] = edgesOrig["OID"]
    num_segExistingMap = edgesOrig.groupby("IDbase").count()["OID"].to_dict()
    edges_dict = edges.reset_index().to_crs("epsg:6500")
    edges_dict = edges_dict.to_dict(orient='records')
    for row_ind in range(len(edges_dict)):
        LS = edges_dict[row_ind]["geometry"]
        num_seg = int(np.ceil(LS.length/delta))
        if num_seg == 1:
            continue
        distances = np.linspace(0, LS.length, num_seg+1)
        points = shapely.MultiPoint([LS.interpolate(distance) for distance in \
                                     distances[:-1]] + [LS.coords[-1]])
        LS = shapely.ops.snap(LS, points, tolerance)
        with warnings.catch_warnings(): #Suppress the warning of points not on 
            # LS. Shaply will first project the point to the line and then split
            warnings.simplefilter("ignore")
            splittedLS = shapely.ops.split(LS,points).geoms
        currentEdge = edges_dict[row_ind].copy()
        num_segExisting = num_segExistingMap[currentEdge["OID"]]
        for sLS_ind, sLS in enumerate(splittedLS):
            # create new edge
            if sLS_ind ==0:
                newID = currentEdge["OID"]
            else:
                newID = currentEdge["OID"]+"_"+str(num_segExisting)
                num_segExisting +=1
                num_segExistingMap[currentEdge["OID"]] += 1
            newGeom = sLS
            newEdge = currentEdge.copy()
            newEdge.update({"OID":newID,"geometry":newGeom})
            newEdges.append(newEdge)
        dropedEdges.append(edges_dict[row_ind]["index"])
    edges = edges.drop(dropedEdges)
    if len(newEdges)>0:
        newEdges = gpd.GeoDataFrame(newEdges, crs="epsg:6500").to_crs(crs)
        edges = pd.concat([edges, newEdges], ignore_index=True)
    edges = edges.reset_index(drop=True).drop(columns = 'index', axis = 1)
    return edges        
    
def formatBridges(minimumHAZUS, connectivity, bridges_gdf):
    ## Format bridge nodes
    if connectivity:
        bnodeDF = bridges_gdf["geometry"].reset_index().rename(columns = {"index":"nodeID"})
        bridges_gdf = bridges_gdf.reset_index().rename(columns={"index":"Location"})
        # bnodeDF = pd.DataFrame({"geometry":bridges_gdf["geometry"]}).reset_index().rename(columns = {"index":"nodeID"})
        # bnodeDF["lat"] = bnodeDF["geometry"].apply(lambda pt:pt.y)
        # bnodeDF["lon"] = bnodeDF["geometry"].apply(lambda pt:pt.x)
        # bnodeDF.drop("geometry", axis=1, inplace=True)
    else:
        bnodeDF = gpd.GeoDataFrame(columns = ["nodeID", "geometry"], crs=bridges_gdf.crs)
    ## Format bridge items
    bridges_gdf["BridgeClass"] = bridges_gdf["STRUCTURE_KIND"].apply(int)*100+bridges_gdf["STRUCTURE_TYPE"].apply(int)
    bridges_gdf = bridges_gdf.rename(columns = {"STRUCTURE_NUMBER":"StructureNumber",\
        "YEAR_BUILT":"YearBuilt", "MAIN_UNIT_SPANS":"NumOfSpans",\
        "MAX_SPAN_LEN_MT":"MaxSpanLength","STATE_CODE":"StateCode",\
        "DEGREES_SKEW":"Skew","DECK_WIDTH_MT":"DeckWidth"})
    # bridges_gdf["StructureNumber"] = bridges_gdf["StructureNumber"].\apply(lambda x: x.replace(" ",""))
    if minimumHAZUS:
        columnsNeededByHAZUS = ["StructureNumber", "geometry", "BridgeClass", "YearBuilt",\
                                "NumOfSpans", "MaxSpanLength", "StateCode", "Skew",\
                                "DeckWidth"]
        if connectivity:
            columnsNeededByHAZUS.append('Location')
        bridges_gdf = bridges_gdf.loc[:,columnsNeededByHAZUS]
    ## Format the hwy_bridges geojson
    bridges_gdf["type"] = "HwyBridge"
    bridgeDict = json.loads(bridges_gdf.to_json())
    # bridgeDict = pd.DataFrame(bridges_gdf)
    # bridgeDict = bridgeDict.reset_index().rename(columns={"index":"location"})
    # bridgeDict = bridgeDict[["ID", "location", "bridgeClass", "yearBuilt", "numOfSpans", "maxSpanLength", "stateCode", "skew", "deckWidth"]]
    # bridgeDict = bridgeDict.sort_values(by = 'ID') 
    # bridgeDict = bridges_gdf.to_dict("records")
    return bnodeDF, bridgeDict
    
def formatRoads(minimumHAZUS, connectivity, maxRoadLength, roads_gdf):
    ## Break long roads into multiple roads
    if maxRoadLength is not None:
        expandedRoads = breakDownLongEdges(roads_gdf, maxRoadLength)
    else:
        expandedRoads = roads_gdf
    if connectivity:
        ## Convert to graph to find the intersection nodes
        graph = momepy.gdf_to_nx(expandedRoads.to_crs("epsg:6500"), approach='primal')
        with warnings.catch_warnings(): #Suppress the warning of disconnected components in the graph
            warnings.simplefilter("ignore")
            nodes, edges, sw = momepy.nx_to_gdf(graph, points=True, lines=True,
                                                spatial_weights=True)
        # The CRS of SimCenter is CRS:84 (equivalent to EPSG:4326)
        # The CRS of US Census is NAD83, which is https://epsg.io/4269
        nodes = nodes.to_crs("epsg:4326")
        edges = edges.to_crs("epsg:4326")
        rnodeDF = nodes
        ### Some edges has start_node as the last point in the geometry and end_node as the first point, check and reorder
        for ind in edges.index:
            start = nodes.loc[edges.loc[ind, "node_start"],"geometry"]
            end = nodes.loc[edges.loc[ind, "node_end"],"geometry"]
            first = shapely.geometry.Point(edges.loc[ind,"geometry"].coords[0])
            last = shapely.geometry.Point(edges.loc[ind,"geometry"].coords[-1])
            #check if first and last are the same
            if (start == first and end == last):
                continue
            elif (start == last and end == first):
                newStartID = edges.loc[ind, "node_end"]
                newEndID = edges.loc[ind, "node_start"]
                edges.loc[ind,"node_start"] = newStartID
                edges.loc[ind,"node_end"] = newEndID
            else:
                print(ind, "th row of roadway has wrong start/first, end/last pairs, likely a bug of momepy.gdf_to_nx function")
        ### Some edges are duplicated, keep only the first one
        # edges = edges[edges.duplicated(['node_start', 'node_end'], keep="first")==False]
        # edges = edges.reset_index(drop=True)
        edges = edges.rename(columns={'node_start': 'StartNode', 'node_end': 'EndNode'})
        edges = edges.drop(columns="mm_len", axis=1)
    else:
        rnodeDF = gpd.GeoDataFrame(columns = ["nodeID", "geometry"], crs=roads_gdf.crs)
        edges = expandedRoads
    ## Format roadways
    ### Format and clean up roadway edges
    road_type = []
    lanes = []
    capacity = []
    edge_id = []
    for row_ind in edges.index:
        mtfcc = edges.loc[row_ind,"MTFCC"]
        road_type.append(ROADTYPE_MAP[mtfcc])
        lanes.append(ROADLANES_MAP[mtfcc])
        capacity.append(ROADCAPACITY_MAP[mtfcc])
        edge_id.append(edges.loc[row_ind,"OID"])
    edges["ID"] = edge_id
    edges["RoadType"] = road_type
    edges["NumOfLanes"] = lanes
    edges["MaxMPH"] = capacity
    if minimumHAZUS:
        columnsNeededByHAZUS=['ID','RoadType','NumOfLanes','MaxMPH', 'geometry']
        if connectivity:
            columnsNeededByHAZUS+=["StartNode", "EndNode"]
        edges = edges[columnsNeededByHAZUS]
    
    #sort the edges
    if maxRoadLength is not None:
        baseID = list(edges["ID"].apply(lambda x:float(x.split("_")[0])))
        segID = list(edges["ID"].apply(lambda x: 0 if len(x.split("_"))==1\
                                           else float(x.split("_")[1])))
        with warnings.catch_warnings(): #Suppress the warning of pandas copy
            warnings.simplefilter("ignore")
            edges['baseID'] = baseID
            edges['segID'] = segID
        edges = edges.sort_values(by=['baseID','segID']).reset_index(drop=True)
        edges = edges.drop(columns=['baseID','segID'],axis=1)
    else:
        edges = edges.sort_values(by="ID").reset_index(drop=True)
    edges['type'] = "Roadway"
    edgesDict = json.loads(edges.to_json())

    ## Format roadway nodes
    # rnodeDF["lat"] = rnodeDF["geometry"].apply(lambda pt:pt.y)
    # rnodeDF["lon"] = rnodeDF["geometry"].apply(lambda pt:pt.x)
    # rnodeDF = rnodeDF.drop("geometry", axis=1)

    return rnodeDF, edgesDict

def formatTunnels(minimumHAZUS, connectivity, tunnels_gdf):
    ## Format tunnel nodes
    # tnodeDF = pd.DataFrame({"geometry":tunnels_gdf["geometry"]}).reset_index().rename(columns = {"index":"nodeID"})
    # tnodeDF["lat"] = tnodeDF["geometry"].apply(lambda pt:pt.y)
    # tnodeDF["lon"] = tnodeDF["geometry"].apply(lambda pt:pt.x)
    # tnodeDF.drop("geometry", axis=1, inplace=True)
    if connectivity:
        tnodeDF = tunnels_gdf["geometry"].reset_index().rename(columns = {"index":"nodeID"})
        tunnels_gdf = tunnels_gdf.reset_index().rename(columns={"index":"Location"})
    else:
        tnodeDF = gpd.GeoDataFrame(columns = ["nodeID", "geometry"], crs=tunnels_gdf.crs)
    ## Format tunnel items
    if "cons_type" not in tunnels_gdf.columns:
        print("consType is not found in the retrived tunnel inventory data. Set as unclassified")
        tunnels_gdf["cons_type"] = "unclassified"
    tunnels_gdf = tunnels_gdf.rename(columns = {"tunnel_number":"TunnelNumber", 
                                                "cons_type":"ConsType"})
    if minimumHAZUS:
        columnsNeededByHAZUS = ["TunnelNumber", "ConsType", "geometry"]
        if connectivity:
            columnsNeededByHAZUS.append('Location')
        tunnels_gdf = tunnels_gdf.loc[:,columnsNeededByHAZUS]
    # tunnels_gdf["ID"] = tunnels_gdf["ID"].apply(lambda x: x.replace(" ",""))
    ## Format the hwy_tunnels dict array
    tunnels_gdf["type"] = "HwyTunnel"
    tunnelDict = json.loads(tunnels_gdf.to_json())
    # tunnelDict = pd.DataFrame(tunnels_gdf)
    # tunnelDict = tunnelDict.reset_index().rename(columns={"index":"location"})
    # tunnelDict = tunnelDict[["ID", "location", "consType"]]
    # tunnelDict = tunnelDict.sort_values("ID")
    # tunnelDict = tunnelDict.to_dict("records")
    return tnodeDF, tunnelDict
    

def combineDict(bnodeDF, bridgesDict, rnodeDF, roadsDict, tnodeDF, tunnelsDict,\
                connectivity, crs="epsg:4326"):
    combinedDict = {'type':'FeatureCollection', 
                    "crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" } },
                    'features':[]}
    combinedDict["features"] += bridgesDict['features']
    combinedDict["features"] += tunnelsDict['features']
    combinedDict["features"] += roadsDict['features']
    if connectivity:
        NumOfBridgeNodes = bnodeDF.shape[0]
        NumOfRoadwayNode = rnodeDF.shape[0]
        NumOfTunnelNodes = tnodeDF.shape[0]
        # Append tunnels to bridges
        tnodeDF["nodeID"] = tnodeDF["nodeID"].apply(lambda x:x + NumOfBridgeNodes)
        for tunnel in tunnelsDict['features']:
            tunnel["properties"]["Location"] = tunnel["properties"]["Location"] + NumOfBridgeNodes
        # Append roadways to tunnels and bridges
        rnodeDF["nodeID"] = rnodeDF["nodeID"].apply(lambda x:x + NumOfBridgeNodes + NumOfTunnelNodes)
        for road in roadsDict['features']:
            road["properties"]["StartNode"] = road["properties"]["StartNode"] + NumOfBridgeNodes + NumOfTunnelNodes
            road["properties"]["EndNode"] = road["properties"]["EndNode"] + NumOfBridgeNodes + NumOfTunnelNodes
    # Create the combined dic
        allNodeDict = pd.concat([bnodeDF, tnodeDF, rnodeDF], axis=0, ignore_index=True)
        allNodeDict["type"] = "TransportationNode"
        allNodeDict = json.loads(allNodeDict.to_json())
        combinedDict["features"]+=allNodeDict['features']
    return combinedDict
# Not used
def combineGeoJSON(bridgesFile, tunnelsFile, roadsFile, savePath):
    # Format the bridge geoJSON
    if bridgesFile is None:
        bridgeJSON = {
            "type": "FeatureCollection",
            "crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" }},
            "features": []
        }
    else:
        BridgesRenameMap = {"STRUCTURE_NUMBER":"ID","geometry":"location", 
            "YEAR_BUILT":"yearBuilt", "MAIN_UNIT_SPANS":"numOfSpans",
            "MAX_SPAN_LEN_MT":"maxSpanLength","STATE_CODE":"stateCode",
            "DEGREES_SKEW":"skew","DECK_WIDTH_MT":"deckWidth"}
        with open(bridgesFile, 'r') as f:
            bridgeJSON = json.load(f)
        for brg in bridgeJSON['features']:
            brg['properties'].update({'type':'hwyBridge'})
            bridgeClass = int(brg['properties']["STRUCTURE_KIND"])*100 + \
                int(brg['properties']["STRUCTURE_TYPE"])
            brg['properties'].update({'bridgeClass':bridgeClass})
            bridgeID = brg['properties']['ID'].replace(" ","")
            brg['properties'].update({'ID':bridgeID})
            for oldName, newName in BridgesRenameMap.items():
                value = brg['properties'].pop(oldName)
                brg['properties'].update({newName : value})
    # Format the tunnel geoJSON
    if tunnelsFile is None:
        tunnelJSON = {
            "type": "FeatureCollection",
            "crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" }},
            "features": []
        }
    else:
        TunnelRenameMap = {"tunnel_number":"ID"}
        with open(tunnelsFile, 'r') as f:
            tunnelJSON = json.load(f)
        for tul in tunnelJSON['features']:
            tul['properties'].update({'type':'hwyTunnel'})
            for oldName, newName in TunnelRenameMap.items():
                value = tul['properties'].pop(oldName)
                tul['properties'].update({newName : value})
            # consType is not available in the national tunnel inventory. Set as
            # unclassifed by default
            tul['properties'].update({'consType':'unclassified'})
            tunnelID = tul['properties']['ID'].replace(" ","")
            tul['properties'].update({'ID':tunnelID})
    # Format the roadway geoJSON
    if roadsFile is None:
        roadJSON = {
            "type": "FeatureCollection",
            "crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" }},
            "features": []
        }
    else:
        RoadRenameMap = {'OID': 'ID'}
        with open(roadsFile, 'r') as f:
            roadJSON = json.load(f)
        for rd in roadJSON['features']:
            rd['properties'].update({'type':'roadway'})
            mtfcc = rd['properties']["MTFCC"]
            rd['properties'].update({'roadType':ROADTYPE_MAP[mtfcc]})
            rd['properties'].update({'lanes':ROADLANES_MAP[mtfcc]})
            rd['properties'].update({'maxMPH':ROADCAPACITY_MAP[mtfcc]})
            for oldName, newName in RoadRenameMap.items():
                value = rd['properties'].pop(oldName)
                rd['properties'].update({newName : value})
    # Combine three geoJSON
    combined = dict()
    combined.update(bridgeJSON)
    combined['features'] = combined['features']  + tunnelJSON['features']
    combined['features'] = combined['features']  + roadJSON['features']
    
    with open(savePath, 'w') as f:
        json.dump(combined, f, indent = 2)
    return
