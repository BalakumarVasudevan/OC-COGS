import os
import requests
import json
import pyodbc
from datetime import datetime, timedelta
import time
import logging


REQUESTS_POST = "POST"
REQUESTS_GET = "GET"

ALL_REQUESTS_METHODS = [REQUESTS_GET, REQUESTS_POST]

REQUESTS_METHOD_MAP = {
	REQUESTS_POST: requests.post,
	REQUESTS_GET: requests.get,
}

# Global vars
rg_by_subs = {}
resources = {}
resources_by_sub = {}
rg_by_owner = {}
rg_list = []
resources_sql_list = []
vmss_sql_list = []
apim_sql_list = []
cosmos_sql_list = []
sb_sql_list = []
cost_by_rg = {}
cost_by_rg_list = []
CONFIG = None
ACCESS_TOKEN = None
DUMMY_DATE = datetime.now()
SUBSCRIPTION_NAME_TO_ID = {}
SUBSCRIPTION_ID_TO_NAME = {}

def print_item(group):
    """Print a ResourceGroup instance."""
    print("\n\n\tName: {}".format(group.name))


def print_properties(props):
    if props and props.provisioning_state:
        print("\tProperties:")
        print("\t\tProvisioning State: {}".format(props.provisioning_state))
    print("\n\n")

def do_requests(url, method=None, headers=None, payload=None, content_type=None):
	if not method or method not in ALL_REQUESTS_METHODS:
		print("Invalid REST request method!")
		return None

	print("\nExecuting {0} request..".format(method))
	if content_type is "json":
		response = REQUESTS_METHOD_MAP[method](url, json=payload, headers=headers)
	else:
		response = REQUESTS_METHOD_MAP[method](url, data=payload, headers=headers)

	print(response.status_code)
	return response

def _get_access_token_payload():
	return {
		"grant_type": CONFIG["AZURE_GRANT_TYPE"],
		"client_id": CONFIG["AZURE_CLIENT_ID"],
		"client_secret": CONFIG["AZURE_CLIENT_SECRET"],
		"resource": CONFIG["AZURE_RESOURCE"]
	}

def _get_access_token():
	url = CONFIG["URLS"]["ACCESS_TOKEN"].format(TENANT_ID=CONFIG["AZURE_TENANT_ID"])
	headers = {'Content-Type': 'application/x-www-form-urlencoded'}

	logging.debug("Getting access token for Tenant: {0}".format(CONFIG["AZURE_TENANT_ID"]))
	
	payload = _get_access_token_payload()
	response = do_requests(url, REQUESTS_POST, headers=headers, payload=payload)
	
	if response.status_code == 200:
		logging.debug("GET access token successful")
		data = json.loads(response.content)
		return data["access_token"]
	else:
		logging.critical("GET access token failed with response code: {0} and message: {1}".format(response.status_code, response.reason))

def _get_unoptimized_clusters(resources):
	for subscription_id, resource_list in resources:
		print("Subscription {0}".format(subscription_id))
		for resource in resource_list:
			if resource["name"].endswith("tp"):
				if "sku" in resource:
					if resource["sku"]["name"] != "Standard_D2_v3" or resource["sku"]["capacity"] != 3:
						print("\n{0}\nSKU: {1}".format(resource["name"], resource["sku"]))

def get_resource_groups_list(subscriptions, headers=None, filter=None, expand=None):
	for subscription in subscriptions:
		rgs_per_sub = []
		subscription_id = subscription["ID"]
		logging.info("Getting resource groups list for subscription {0}".format(subscription_id))
		url = CONFIG["URLS"]["LIST_RESOURCEGROUPS"].format(SUBSCRIPTION_ID=subscription_id)
		if filter:
			url += "&$filter={0}".format(filter)
		if expand:
			url += "&$expand={0}".format(expand)

		while url:
			response = do_requests(url, REQUESTS_GET, headers=headers)

			if response.status_code == 200:
				data = json.loads(response.content)
				rgs_per_sub += data["value"]
				if "nextLink" in data:
					url = data["nextLink"]
				else:
					url = None
			elif response.status_code == 401:
				logging.error("Unauthorized error for Subscription: {0}".format(subscription_id))
				break
			else:
				logging.error("[{0}]: Error getting RG list. Status Code:{1}".format(__name__, response.status_code))
		rg_by_subs[subscription_id] = rgs_per_sub

def get_resources_list(subscriptions, headers=None, filter=None, expand=None):
	for subscription in subscriptions:
		resources_per_sub = []
		subscription_id = subscription["ID"]
		logging.info("Getting resources for subscription {0}".format(subscription_id))
		url = CONFIG["URLS"]["LIST_RESOURCES"].format(SUBSCRIPTION_ID=subscription_id)
		if filter:
			url += "&$filter={0}".format(filter)
		if expand:
			url += "&$expand={0}".format(expand)
		
		while url:
			response = do_requests(url, REQUESTS_GET, headers=headers)

			if response.status_code == 200:
				data = json.loads(response.content)
				resources_per_sub += data["value"]
				if "nextLink" in data:
					url = data["nextLink"]
				else:
					url = None
			elif response.status_code == 401:
				logging.error("Unauthorized error for Subscription: {0}".format(subscription_id))
				break
			else:
				logging.error("[{0}]: Error getting Resources list. \nStatus Code:{1} \nReason: {1}".format(__name__, response.status_code, response.reason))
				break
		
		resources[subscription_id] = resources_per_sub

	return resources

def get_tags_list(subscription_id, headers=None):
	url = CONFIG["URLS"]["LIST_TAGS"].format(SUBSCRIPTION_ID=subscription_id)

	response = do_requests(url, REQUESTS_GET, headers=headers)

	if response.status_code == 200:
		data = json.loads(response.content)
		print(json.dumps(data["value"], indent=4))
	else:
		print(response.status_code)

def get_activity_logs_list(subscription_id, headers=None):
	url = CONFIG["URLS"]["LIST_ACTIVITY_LOGS"].format(SUBSCRIPTION_ID=subscription_id)
	print(url)

	response = do_requests(url, REQUESTS_GET, headers=headers)

	if response.status_code == 200:
		data = json.loads(response.content)
		print(data["value"])
	else:
		print(response.status_code)

def get_all_unoptimized_clusters_list(headers=None, filter=None):
	resources = []
	url = CONFIG["URLS"]["LIST_RESOURCES"].format(SUBSCRIPTION_ID=subscription_id)
	if filter:
		url += "&$filter={0}".format(filter)
	if expand:
		url += "&$expand={0}".format(expand)
	print(url)

def get_cost_by_scope_list(subscriptions, scope=None, headers=None):
	for subscription_id in subscription_ids:
		resources_per_sub = []
		print("Getting resources for subscription {0}".format(subscription_id))
		url = CONFIG["URLS"]["LIST_RESOURCES"].format(SUBSCRIPTION_ID=subscription_id)
		if filter:
			url += "&$filter={0}".format(filter)
		if expand:
			url += "&$expand={0}".format(expand)
		
		while url:
			response = do_requests(url, REQUESTS_GET, headers=headers)

def print_list_of_orphan_rgs_older_than_n_days(days=1):
	global rg_by_owner
	global SUBSCRIPTION_ID_TO_NAME
	print("\n\nList of orphan RGs")
	cat_by_sub = {}
	for rg in rg_by_owner["orphan"]["resource_groups"]:
		sub = rg["subscription"]
		created_time = datetime.strptime(rg["createdDate"][:23], CONFIG["DATES"]["READ_DATE_FORMAT"])

		if sub not in cat_by_sub:
			cat_by_sub[sub] = []
		if rg["name"] not in cat_by_sub[sub] and (created_time < datetime.now() - timedelta(days=days)):
			cat_by_sub[sub].append(rg["name"])

	for sub, rgs in cat_by_sub.items():
		print("\n\n*** Subscription: {0} ***".format(SUBSCRIPTION_ID_TO_NAME[sub]))
		for rg in rgs:
			if "oc-local-" not in rg:
				print(rg)

def get_resource_groups_by_owner():
	for subscription_id, rgs in rg_by_subs.items():
		print("Number of RGs in subscription: {0} is {1}".format(subscription_id, len(rgs)))
		for rg in rgs:
			tags = rg["tags"] if "tags" in rg else None
			owner_tag_name = None
			env_tag_name = None
			can_be_deleted_tag_name = None
			owner_tag = "orphan"
			env_tag = None
			can_be_deleted_tag = None

			if tags:
				if "owner" in tags:
					owner_tag_name = "owner"
				elif "Owner" in tags:
					owner_tag_name = "Owner"
				owner_tag = rg["tags"][owner_tag_name] if (tags and owner_tag_name) else "orphan"

				if "ocenv" in tags:
					env_tag_name = "ocenv"
				elif "Ocenv" in tags:
					env_tag_name = "Ocenv"
				env_tag = rg["tags"][env_tag_name] if (tags and env_tag_name) else None

				if "canbedeleted" in tags:
					can_be_deleted_tag_name = "canbedeleted"
				elif "Canbedeleted" in tags:
					can_be_deleted_tag_name = "Canbedeleted"
				can_be_deleted_tag = rg["tags"][can_be_deleted_tag_name] if (tags and can_be_deleted_tag_name) else None
			created_time = datetime.strptime(rg["createdTime"][:23], CONFIG["DATES"]["READ_DATE_FORMAT"])
			
			if owner_tag not in rg_by_owner:
				rg_by_owner[owner_tag] = {
					"resource_groups": [],
					"total_cost": 0.0
				}
			
			rg_by_owner[owner_tag]["resource_groups"].append({
						"subscription": subscription_id,
						"name": rg["name"],
						"createdDate": rg["createdTime"],
						"cost": 0.0
					})
			rg_list.append((
				rg["name"],
				subscription_id,
				owner_tag,
				env_tag,
				created_time,
				# created_time.strftime(WRITE_DATE_FORMAT),
				None,
				1 if can_be_deleted_tag and can_be_deleted_tag is not None else 0
				))

def get_cost_by_rg_current_month(headers=None):
	start = time.time()
	for subscription in CONFIG["AZURE_SUBSCRIPTIONS"]:
		subscription_id = subscription["ID"]
		print("\nGetting current month RG cost for subscription {0}\n".format(subscription_id))
		url = CONFIG["URLS"]["COST_MGMT_BY_SUB"].format(SUBSCRIPTION_ID=subscription_id)
		print(url)
		request_body = {
			"type":"ActualCost",
			"dataSet": {
				"granularity":"None",
				"aggregation": {
					"totalCost": {
						"name":"PreTaxCost",
						"function":"Sum"
					}
				},
				"grouping": [
					{
						"type":"Dimension",
						"name":"ResourceGroupName"
					}
				],
				# "include": ["Tags"]
			},
			"timeframe":"MonthToDate"
		}

		response = do_requests(url, REQUESTS_POST, headers=headers, payload=request_body, content_type="json")

		if response.status_code == 200:
			data = json.loads(response.content)
			rows = data["properties"]["rows"]
			for row in rows:
				if row:
					# print(row)
					rg_name = row[1]
					cost = row[0]
					cost_by_rg[rg_name] = {
						"currentMonth": cost,
						"subscription": subscription_id,
						"lastMonth": 0.
					}
		elif response.status_code == 401:
			print("[Cost API][Current Month] Unauthorized Error for subscription {0}".format(subscription_id))
		else:
			print("[Cost API][Current Month] Error code: {0}".format(response.status_code))

	end = time.time()
	print("Time to get RGs cost for Current Month: {0}".format(end - start))

def get_cost_by_rg_last_month(headers=None):
	start = time.time()
	for subscription in CONFIG["AZURE_SUBSCRIPTIONS"]:
		subscription_id = subscription["ID"]
		print("\nGetting last month RG cost for subscription {0}\n".format(subscription_id))
		url = CONFIG["URLS"]["COST_MGMT_BY_SUB"].format(SUBSCRIPTION_ID=subscription_id)
		print(url)
		request_body = {
			"type":"ActualCost",
			"dataSet": {
				"granularity":"None",
				"aggregation": {
					"totalCost": {
						"name":"PreTaxCost",
						"function":"Sum"
					}
				},
				"grouping": [
					{
						"type":"Dimension",
						"name":"ResourceGroupName"
					}
				],
				# "include": ["Tags"]
			},
			"timeframe":"TheLastmonth"
		}

		response = do_requests(url, REQUESTS_POST, headers=headers, payload=request_body, content_type="json")

		if response.status_code == 200:
			data = json.loads(response.content)
			rows = data["properties"]["rows"]
			for row in rows:
				if row:
					rg_name = row[1]
					cost = row[0]
					if rg_name in cost_by_rg:
						cost_by_rg[rg_name]["lastMonth"] = cost
		elif response.status_code == 401:
			print("[Cost API][Last Month] Unauthorized Error for subscription {0}".format(subscription_id))
		else:
			print("[Cost API][Current Month] Error code: {0}".format(response.status_code))
	end = time.time()
	print("Time to get RGs cost for Last Month: {0}".format(end - start))

def get_cost_by_rg_list():
	for rg_name, rg_values in cost_by_rg.items():
		cost_by_rg_list.append(
			(rg_name, rg_values["subscription"], rg_values["currentMonth"], rg_values["lastMonth"])
		)

def get_cost_by_rg_owner():
	for owner, rg_info in rg_by_owner.items():
		for rg in rg_info["resource_groups"]:
			rg_name = rg["name"]
			
			if rg_name in cost_by_rg:
				cost = cost_by_rg[rg_name]
				rg["cost"] += cost

				rg_info["total_cost"] += cost

def upsert_rg_list_to_sql():
	global cursor
	global cnxn
	global CONFIG
	start = time.time()
	cursor.execute(CONFIG["SQL"]["RG_TRUNCATE_SQL"])
	print(rg_list)
	cursor.executemany(CONFIG["SQL"]["RG_INSERT_SQL"], rg_list)
	cnxn.commit()
	end = time.time()
	print("Time to upsert RGs to Azure SQL: {0}".format(end - start))

def upsert_rg_cost_list_to_sql():
	global cursor
	global cnxn
	global CONFIG
	start = time.time()
	cursor.execute(CONFIG["SQL"]["RG_COST_TRUNCATE_SQL"])
	cursor.executemany(CONFIG["SQL"]["RG_COST_INSERT_SQL"], cost_by_rg_list)
	cnxn.commit()
	end = time.time()
	print("Time to upsert RGs cost to Azure SQL: {0}".format(end - start))

def upsert_all_resources_list_to_sql(all_resources_list):
	global cursor
	global cnxn
	global CONFIG
	start = time.time()
	cursor.execute(CONFIG["SQL"]["RESOURCES_TRUNCATE_SQL"])
	cursor.executemany(CONFIG["SQL"]["RESOURCES_INSERT_SQL"], all_resources_list)
	cnxn.commit()
	end = time.time()
	print("Time to upsert all Resources to Azure SQL: {0}".format(end - start))

def upsert_vmss_list_to_sql(vmss_list):
	global cursor
	global cnxn
	global CONFIG
	start = time.time()
	cursor.execute(CONFIG["SQL"]["VMSS_TRUNCATE_SQL"])
	cursor.executemany(CONFIG["SQL"]["VMSS_INSERT_SQL"], vmss_list)
	cnxn.commit()
	end = time.time()
	print("Time to upsert VMSS list to Azure SQL: {0}".format(end - start))

def upsert_apim_list_to_sql(apim_list):
	global cursor
	global cnxn
	global CONFIG
	start = time.time()
	cursor.execute(CONFIG["SQL"]["APIM_TRUNCATE_SQL"])
	cursor.executemany(CONFIG["SQL"]["APIM_INSERT_SQL"], apim_list)
	cnxn.commit()
	end = time.time()
	print("Time to upsert APIM list to Azure SQL: {0}".format(end - start))

def upsert_cosmos_list_to_sql(cosmos_list):
	global cursor
	global cnxn
	global CONFIG
	start = time.time()
	cursor.execute(CONFIG["SQL"]["COSMOS_TRUNCATE_SQL"])
	cursor.executemany(CONFIG["SQL"]["COSMOS_INSERT_SQL"], cosmos_list)
	cnxn.commit()
	end = time.time()
	print("Time to upsert COSMOS list to Azure SQL: {0}".format(end - start))

def upsert_sb_list_to_sql(sb_list):
	global cursor
	global cnxn
	global CONFIG
	start = time.time()
	cursor.execute(CONFIG["SQL"]["SB_TRUNCATE_SQL"])
	cursor.executemany(CONFIG["SQL"]["SB_INSERT_SQL"], sb_list)
	cnxn.commit()
	end = time.time()
	print("Time to upsert SB list to Azure SQL: {0}".format(end - start))

def update_last_refreshed():
	global cursor
	global cnxn
	global CONFIG
	cursor.execute(CONFIG["SQL"]["UPDATE_LAST_USED_SQL"], datetime.now())
	cnxn.commit()
	print("Updated last refreshed timestamp!")

def get_filter(key, value, clause):
	return "{0} {1} '{2}'".format(key, clause, value)

def get_all_resources_list_helper(headers=None, expand=None):
	global resources_sql_list
	resources_per_sub = get_resources_list(CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, expand=expand)
	for subscription_id, resources_list in resources_per_sub.items():
		for resource in resources_list:
			sku = resource["sku"] if "sku" in resource else None
			rg_name = resource["id"].split('/')[4]
			resource_provider = resource["type"].split('/')[0]
			created_time = datetime.strptime(resource["createdTime"][:23], CONFIG["DATES"]["READ_DATE_FORMAT"])
			resources_sql_list.append(
				(
					subscription_id,
					rg_name,
					resource["name"],
					resource_provider,
					resource["type"],
					json.dumps(sku),
					created_time
				)
			)

	return resources_sql_list

def get_vmss_resource_list_helper(headers=None, expand=None):
	global vmss_sql_list
	filter = get_filter("resourceType", "Microsoft.Compute/virtualMachineScaleSets", "eq")
	vmss_per_sub = get_resources_list(CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, filter=filter, expand=expand)
	print(json.dumps(vmss_per_sub, indent=4))
	for subscription_id, vmss_list in vmss_per_sub.items():
		for vmss in vmss_list:
			sku = vmss["sku"] if "sku" in vmss else None
			rg_name = vmss["id"].split('/')[4]
			created_time = datetime.strptime(vmss["createdTime"][:23], CONFIG["DATES"]["READ_DATE_FORMAT"])
			vmss_sql_list.append(
				(
					subscription_id,
					rg_name,
					vmss["name"],
					sku["capacity"] if sku and "capacity" in sku else None,
					created_time,
					sku["name"] if sku and "name" in sku else None,
					None,
					sku["tier"] if sku and "tier" in sku else None,
					vmss["tags"]["clusterName"] if ("tags" in vmss and "clusterName" in vmss["tags"]) else None
				)
			)

	return vmss_sql_list

def get_apim_resource_list_helper(headers=None, expand=None):
	global apim_sql_list
	filter = get_filter("resourceType", "Microsoft.ApiManagement/service", "eq")
	apim_per_sub = get_resources_list(CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, filter=filter, expand=expand)
	print(json.dumps(apim_per_sub, indent=4))
	for subscription_id, apim_list in apim_per_sub.items():
		for apim in apim_list:
			sku = apim["sku"] if "sku" in apim else None
			rg_name = apim["id"].split('/')[4]
			created_time = datetime.strptime(apim["createdTime"][:23], CONFIG["DATES"]["READ_DATE_FORMAT"])
			apim_sql_list.append(
				(
					subscription_id,
					rg_name,
					apim["name"],
					sku["capacity"] if sku and "capacity" in sku else None,
					created_time,
					sku["name"] if sku and "name" in sku else None
				)
			)

	return apim_sql_list

def get_cosmos_resource_list_helper(headers=None, expand=None):
	global cosmos_sql_list
	filter = get_filter("resourceType", "Microsoft.DocumentDB/databaseAccounts", "eq")
	cosmos_per_sub = get_resources_list(CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, filter=filter, expand=expand)
	print(json.dumps(cosmos_per_sub, indent=4))
	for subscription_id, cosmos_list in cosmos_per_sub.items():
		for cosmos in cosmos_list:
			rg_name = cosmos["id"].split('/')[4]
			created_time = datetime.strptime(cosmos["createdTime"][:23], CONFIG["DATES"]["READ_DATE_FORMAT"])
			changed_time = datetime.strptime(cosmos["changedTime"][:23], CONFIG["DATES"]["READ_DATE_FORMAT"])
			cosmos_sql_list.append(
				(
					subscription_id,
					rg_name,
					cosmos["name"],
					None,
					cosmos["kind"],
					cosmos["location"],
					created_time,
					changed_time
				)
			)

	return cosmos_sql_list

def get_sb_resource_list_helper(headers=None, expand=None):
	global sb_sql_list
	filter = get_filter("resourceType", "Microsoft.ServiceBus/namespaces", "eq")
	sb_per_sub = get_resources_list(CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, filter=filter, expand=expand)
	print(json.dumps(sb_per_sub, indent=4))
	for subscription_id, sb_list in sb_per_sub.items():
		for sb in sb_list:
			sku = sb["sku"] if "sku" in sb else None
			rg_name = sb["id"].split('/')[4]
			created_time = datetime.strptime(sb["createdTime"][:23], CONFIG["DATES"]["READ_DATE_FORMAT"])
			changed_time = datetime.strptime(sb["changedTime"][:23], CONFIG["DATES"]["READ_DATE_FORMAT"])
			capacity = sku["capacity"] if sku and "capacity" in sku else None
			sku_name = sku["name"] if sku and "name" in sku else None
			tier = sku["tier"] if sku and "tier" in sku else None
			sb_sql_list.append(
				(
					subscription_id,
					rg_name,
					sb["name"],
					capacity,
					created_time,
					changed_time,
					tier,
					sku_name,
					sb["location"]
				)
			)

	return sb_sql_list

def _load_config():
	global CONFIG
	script_dir = os.path.dirname(os.path.abspath(__file__))
	relative_path = "config\config.json"
	config_file_path = os.path.join(script_dir, relative_path)
	with open(config_file_path) as config_file:
		config_data = json.load(config_file)
	CONFIG = config_data

def _load_db_cnxn():
	db_config = CONFIG["DB"]
	global cnxn
	global cursor
	db_connection_string = CONFIG["DB"]["ODBC_CONNECTION_STR"].format(
			DRIVER=db_config["DRIVER"],
			DB_SERVER=db_config["SERVER_NAME"],
			DB_NAME=db_config["NAME"],
			DB_USERNAME=db_config["USERNAME"],
			DB_PWD=db_config["PWD"]
	)
	cnxn = pyodbc.connect(db_connection_string)
	cursor = cnxn.cursor()

def main():
	_load_config()
	_load_db_cnxn()
	global SUBSCRIPTION_NAME_TO_ID
	global SUBSCRIPTION_ID_TO_NAME
	SUBSCRIPTION_NAME_TO_ID = {sub["NAME"]: sub["ID"] for sub in CONFIG["AZURE_SUBSCRIPTIONS"]}
	SUBSCRIPTION_ID_TO_NAME = {sub["ID"]: sub["NAME"] for sub in CONFIG["AZURE_SUBSCRIPTIONS"]}

	print("Refreshing access token")
	ACCESS_TOKEN = _get_access_token()
	headers = {"Authorization": 'Bearer {0}'.format(ACCESS_TOKEN)}
	expand = "createdTime,changedTime"

	vmss_list = get_vmss_resource_list_helper(headers=headers, expand=expand)
	apim_list = get_apim_resource_list_helper(headers=headers, expand=expand)
	cosmos_list = get_cosmos_resource_list_helper(headers=headers, expand=expand)
	service_bus_list = get_sb_resource_list_helper(headers=headers, expand=expand)
	all_resources_list = get_all_resources_list_helper(headers=headers, expand=expand)

	get_resource_groups_list(CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, filter=None, expand=expand)
	# get_tags_list(AZURE_SUBSCRIPTION_ID_1, headers=headers)
	# get_activity_logs_list(AZURE_SUBSCRIPTION_ID, headers=headers)

	get_resource_groups_by_owner()
	print_list_of_orphan_rgs_older_than_n_days(days=14)
	get_cost_by_rg_current_month(headers=headers)
	get_cost_by_rg_last_month(headers=headers)
	get_cost_by_rg_list()

	# get_cost_by_rg_owner()

	upsert_all_resources_list_to_sql(all_resources_list)
	upsert_rg_list_to_sql()
	upsert_rg_cost_list_to_sql()
	upsert_vmss_list_to_sql(vmss_list)
	upsert_apim_list_to_sql(apim_list)
	upsert_cosmos_list_to_sql(cosmos_list)
	upsert_sb_list_to_sql(service_bus_list)
	update_last_refreshed()

if __name__ == '__main__':
	logging.basicConfig(level=logging.DEBUG)
	main()
