import http.client
import ssl
import base64
import json
from datetime import datetime, timezone, timedelta
import os
from fastapi import FastAPI, APIRouter, Query
import uvicorn

app = FastAPI(
    title="Noah's Magical PCO<->Discord Bridge",
    description="API used to figure out which techs are scheduled for each day and their corresponding discord Ids",
    version="1.0.0",
)

debug = True
planType = None
utc_offset = timezone(timedelta(hours=-6)) 
application_id = None
secret = None
main = APIRouter(tags=["Main"])
debug = APIRouter(prefix="/mini", tags=["Mini"])


if os.path.exists("creds.json"):
    with open('creds.json', 'r') as file:
        creds_data = json.load(file)
        planning_center_creds = creds_data.get('planning_center', {})
        application_id = planning_center_creds.get('application_id')
        secret = planning_center_creds.get('secret')

def queryPCO(url):
    global debug, application_id, secret
    HOST = 'api.planningcenteronline.com'
    full_url = f"/services/v2/{url}"  
    conn = http.client.HTTPSConnection(HOST, context=ssl._create_unverified_context())
    
    auth = base64.b64encode(f'{application_id}:{secret}'.encode()).decode()
    headers = {
        'Authorization': f'Basic {auth}',
        'Content-Type': 'application/json'
    }
    
    if debug:
        print(f"#Debug: Querying PCO API: {full_url}")

    try:
        conn.request('GET', full_url, headers=headers)
        response = conn.getresponse()
        data = response.read().decode()
        return json.loads(data) if data else None 
    except Exception as e:
        print(f"Error querying PCO API: {e}")
        return None
    finally:
        conn.close()

@debug.get("/ServiceIDs")
def getServiceIDs():
    global debug
    url = "service_types"
    response = queryPCO(url)
    if response and "data" in response:
        return [item["id"] for item in response["data"]]
    return []

@debug.get("/TodayService")
def getTodayService(today=datetime.now(utc_offset).strftime("%Y-%m-%d")):
    global debug, planType, utc_offset

    ids = getServiceIDs()
    if debug:
        print ("#Debug: Service Types:") 
        print(ids)
    for id in ids:
        url = f"service_types/{id}/plans?filter=future&per_page=1"
        response = queryPCO(url)
        if not response or "data" not in response or not response["data"]:
            continue  
        plan = response["data"][0] 
        plan_date = plan["attributes"]["sort_date"][:10]  # Extract YYYY-MM-DD
        if plan_date == today:
            print("Today's Service is " + plan["id"])
            planType = id
            return plan["id"]  
    print("No service found!")
    return None

@debug.get("/AllTechs")
def getAllTechs(
    today: str = datetime.now(utc_offset).strftime("%Y-%m-%d"),
    nameMode: bool = Query(False)
):
    global debug, planType
    serviceID = getTodayService(today)
    url = f"service_types/{planType}/plans/{serviceID}/team_members"

    technicians = []
    
    for person in queryPCO(url).get("data", []):
        position = person["attributes"].get("team_position_name", "")
        name = person["attributes"].get("name", "")
        
        if "Technician" in position:
            print(name)
            if nameMode:
              technicians.append(name)
            else:
              technicians.append(person["relationships"]["person"]["data"].get("id", ""))

    print(technicians)
    return technicians

@debug.get("/SoundTechs")
def getSoundTechs(today=datetime.now(utc_offset).strftime("%Y-%m-%d"),nameMode=False):
    global debug, planType
    serviceID = getTodayService(today)
    url = f"service_types/{planType}/plans/{serviceID}/team_members"

    technicians = []
    
    for person in queryPCO(url).get("data", []):
        position = person["attributes"].get("team_position_name", "")
        name = person["attributes"].get("name", "")
        
        if "Sound Technician" in position:
            print(name)
            if nameMode:
              technicians.append(name)
            else:
              technicians.append(person["relationships"]["person"]["data"].get("id", ""))

    print(technicians)
    return technicians


@debug.get("/DiscordIDs")
def getDiscordIDs(PCO_ids):
    global debug, planType
    discordID = []
    
    for personID in PCO_ids:
        url = f"people/{personID}/"
        print(f"#Debug: Querying URL: {url}")
        
        response = queryPCO(url)

        if not response or "data" not in response:
            print(f"#Debug: No data found for person ID: {personID}")
            continue  # Skip if no data found

        person_data = response["data"]["attributes"]
        notes = person_data.get("notes", "")

        print(f"#Debug: Found Discord ID: {notes} for Person ID: {personID}")
        discordID.append(notes)
    
    return discordID

@debug.get("/StartTime")
def getPlanStartTime(plan_id):
    global debug, planType
    url = f"service_types/{planType}/plans/{plan_id}/plan_times"
    response = queryPCO(url)

    if not response or "data" not in response:
        print(f"#Debug: No plan times found for plan {plan_id}")
        return None

    for plan_time in response["data"]:
        if plan_time["attributes"].get("name") is None:
            start_time = plan_time["attributes"].get("starts_at", None)
            if debug: print(f"#Debug: Found start time {start_time} for plan {plan_id}")

            utc_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            local_time = utc_time.astimezone(utc_offset)  

            formatted_time = local_time.isoformat()
            print(f"Returning Start Time: {formatted_time}")
            return formatted_time
        
    print(f"#Debug: No unnamed plan time found for plan {plan_id}")
    return None

@main.get("/AllTechs")
def AllTechs(today=datetime.now(utc_offset).strftime("%Y-%m-%d")):
    return getDiscordIDs(getAllTechs(today))

@main.get("/SoundTechs")
def soundTechs(today=datetime.now(utc_offset).strftime("%Y-%m-%d")):
    return getDiscordIDs(getSoundTechs(today))

@main.get("/StartTimes")
def getStartTime(today=datetime.now(utc_offset).strftime("%Y-%m-%d")):
    return getPlanStartTime(getTodayService(today))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

app.include_router(main)
app.include_router(debug)
