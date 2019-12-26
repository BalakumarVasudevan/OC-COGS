import os
import requests
import json
import pyodbc
from datetime import datetime, timedelta
import time
import logging

class COGSResourceManager(object):
	"""
		Manages the Azure Resources for COGS.
	"""

	REQUESTS_POST = "POST"
	REQUESTS_GET = "GET"

	ALL_REQUESTS_METHODS = [REQUESTS_GET, REQUESTS_POST]

	REQUESTS_METHOD_MAP = {
		REQUESTS_POST: requests.post,
		REQUESTS_GET: requests.get,
	}

	def __init__(self):
		self.CONFIG = None
		self.ACCESS_TOKEN = None
		self.DUMMY_DATE = datetime.now()

		self.rg_by_subs = {}
		self.resources = {}
		self.resources_by_sub = {}
		self.rg_by_owner = {}
		self.rg_list = []
		self.resources_sql_list = []
		self.vmss_sql_list = []
		self.apim_sql_list = []
		self.cosmos_sql_list = []
		self.sb_sql_list = []
		self.cost_by_rg = {}
		self.cost_by_rg_list = []

		self._load_config()
		self._load_db_cnxn()
		self.SUBSCRIPTION_NAME_TO_ID = {sub["NAME"]: sub["ID"] for sub in self.CONFIG["AZURE_SUBSCRIPTIONS"]}
		self.SUBSCRIPTION_ID_TO_NAME = {sub["ID"]: sub["NAME"] for sub in self.CONFIG["AZURE_SUBSCRIPTIONS"]}


	@staticmethod
	def do_requests(url, method=None, headers=None, payload=None, content_type=None):
		if not method or method not in COGSResourceManager.ALL_REQUESTS_METHODS:
			logging.error("Invalid REST request method: {0}".format(method))
			return None

		logging.debug("Executing {0} request".format(method))
		if content_type is "json":
			response = COGSResourceManager.REQUESTS_METHOD_MAP[method](url, json=payload, headers=headers)
		else:
			response = COGSResourceManager.REQUESTS_METHOD_MAP[method](url, data=payload, headers=headers)

		logging.debug("Response code: {0}".format(response.status_code))
		return response

	def _get_access_token_payload(self):
		return {
			"grant_type": self.CONFIG["AZURE_GRANT_TYPE"],
			"client_id": self.CONFIG["AZURE_CLIENT_ID"],
			"client_secret": self.CONFIG["AZURE_CLIENT_SECRET"],
			"resource": self.CONFIG["AZURE_RESOURCE"]
		}

	def _get_access_token(self):
		url = self.CONFIG["URLS"]["ACCESS_TOKEN"].format(TENANT_ID=self.CONFIG["AZURE_TENANT_ID"])
		headers = {'Content-Type': 'application/x-www-form-urlencoded'}

		logging.debug("Getting access token for Tenant: {0}".format(self.CONFIG["AZURE_TENANT_ID"]))
		
		payload = self._get_access_token_payload()
		response = self.do_requests(url, COGSResourceManager.REQUESTS_POST, headers=headers, payload=payload)
		
		if response.status_code == 200:
			logging.debug("GET access token successful")
			data = json.loads(response.content)
			return data["access_token"]
		else:
			logging.critical("GET access token failed with response code: {0} and message: {1}".format(response.status_code, response.reason))

	@staticmethod
	def _get_unoptimized_clusters(resources):
		for subscription_id, resource_list in resources:
			for resource in resource_list:
				if resource["name"].endswith("tp"):
					if "sku" in resource:
						if resource["sku"]["name"] != "Standard_D2_v3" or resource["sku"]["capacity"] != 3:
							print("\n{0}\nSKU: {1}".format(resource["name"], resource["sku"]))


	def get_resource_groups_list(self, subscriptions, headers=None, filter=None, expand=None):
		for subscription in subscriptions:
			rgs_per_sub = []
			subscription_id = subscription["ID"]
			logging.info("Getting resource groups list for subscription {0}".format(subscription_id))
			url = self.CONFIG["URLS"]["LIST_RESOURCEGROUPS"].format(SUBSCRIPTION_ID=subscription_id)
			if filter:
				url += "&$filter={0}".format(filter)
			if expand:
				url += "&$expand={0}".format(expand)

			while url:
				response = self.do_requests(url, COGSResourceManager.REQUESTS_GET, headers=headers)

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
			
			logging.info("Done.")
			self.rg_by_subs[subscription_id] = rgs_per_sub


	def get_resources_list(self, subscriptions, headers=None, filter=None, expand=None):
		for subscription in subscriptions:
			resources_per_sub = []
			subscription_id = subscription["ID"]
			logging.info("Getting resources for subscription {0}".format(subscription_id))
			url = self.CONFIG["URLS"]["LIST_RESOURCES"].format(SUBSCRIPTION_ID=subscription_id)
			if filter:
				url += "&$filter={0}".format(filter)
			if expand:
				url += "&$expand={0}".format(expand)
			
			while url:
				response = self.do_requests(url, COGSResourceManager.REQUESTS_GET, headers=headers)

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
			
			logging.info("Done.")
			self.resources[subscription_id] = resources_per_sub

		return self.resources


	def get_tags_list(self, subscription_id, headers=None):
		url = self.CONFIG["URLS"]["LIST_TAGS"].format(SUBSCRIPTION_ID=subscription_id)

		response = self.do_requests(url, COGSResourceManager.REQUESTS_GET, headers=headers)

		if response.status_code == 200:
			data = json.loads(response.content)
			logging.debug(json.dumps(data["value"], indent=4))
		else:
			logging.error(response.status_code)


	def print_activity_logs_list(self, subscription_id, headers=None):
		url = self.CONFIG["URLS"]["LIST_ACTIVITY_LOGS"].format(SUBSCRIPTION_ID=subscription_id)
		logging.debug("Activity list url: {0}".format(url))

		response = self.do_requests(url, COGSResourceManager.REQUESTS_GET, headers=headers)

		if response.status_code == 200:
			data = json.loads(response.content)
			logging.debug(data["value"])
		else:
			logging.error(response.status_code)


	def print_all_unoptimized_clusters_list(self, headers=None, filter=None):
		resources = []
		url = self.CONFIG["URLS"]["LIST_RESOURCES"].format(SUBSCRIPTION_ID=subscription_id)
		if filter:
			url += "&$filter={0}".format(filter)
		if expand:
			url += "&$expand={0}".format(expand)
		logging.info(url)


	def get_cost_by_scope_list(self, subscriptions, scope=None, headers=None):
		for subscription_id in subscription_ids:
			resources_per_sub = []
			logging.info("Getting resources for subscription {0}".format(subscription_id))
			url = self.CONFIG["URLS"]["LIST_RESOURCES"].format(SUBSCRIPTION_ID=subscription_id)
			if filter:
				url += "&$filter={0}".format(filter)
			if expand:
				url += "&$expand={0}".format(expand)
			
			while url:
				response = do_requests(url, COGSResourceManager.REQUESTS_GET, headers=headers)
			
			logging.info("Done.")


	def print_list_of_orphan_rgs_older_than_n_days(self, days=1):
		cat_by_sub = {}
		logging.info("List of Orphan RGs older than {0} days".format(days))
		for rg in self.rg_by_owner["orphan"]["resource_groups"]:
			sub = rg["subscription"]
			created_time = datetime.strptime(rg["createdDate"][:23], self.CONFIG["DATES"]["READ_DATE_FORMAT"])

			if sub not in cat_by_sub:
				cat_by_sub[sub] = []
			if rg["name"] not in cat_by_sub[sub] and (created_time < datetime.now() - timedelta(days=days)):
				cat_by_sub[sub].append(rg["name"])

		for sub, rgs in cat_by_sub.items():
			logging.info("*** Subscription: {0} ***".format(self.SUBSCRIPTION_ID_TO_NAME[sub]))
			for rg in rgs:
				if "oc-local-" not in rg:
					logging.info(rg)

	def get_resource_groups_by_owner(self):
		for subscription_id, rgs in self.rg_by_subs.items():
			logging.info("Number of RGs in subscription: {0} is {1}".format(subscription_id, len(rgs)))
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
				created_time = datetime.strptime(rg["createdTime"][:23], self.CONFIG["DATES"]["READ_DATE_FORMAT"])
				
				if owner_tag not in self.rg_by_owner:
					self.rg_by_owner[owner_tag] = {
						"resource_groups": [],
						"total_cost": 0.0
					}
				
				self.rg_by_owner[owner_tag]["resource_groups"].append({
							"subscription": subscription_id,
							"name": rg["name"],
							"createdDate": rg["createdTime"],
							"cost": 0.0
						})
				
				self.rg_list.append((
					rg["name"],
					subscription_id,
					owner_tag,
					env_tag,
					created_time,
					None,
					1 if can_be_deleted_tag and can_be_deleted_tag is not None else 0
					))

	def get_cost_by_rg_current_month(self, headers=None):
		start = time.time()
		for subscription in self.CONFIG["AZURE_SUBSCRIPTIONS"]:
			subscription_id = subscription["ID"]
			logging.info("Getting current month RG cost for subscription {0}".format(subscription_id))
			url = self.CONFIG["URLS"]["COST_MGMT_BY_SUB"].format(SUBSCRIPTION_ID=subscription_id)
			logging.debug("url: {0}".format(url))
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

			response = self.do_requests(url, COGSResourceManager.REQUESTS_POST, headers=headers, payload=request_body, content_type="json")

			if response.status_code == 200:
				data = json.loads(response.content)
				rows = data["properties"]["rows"]
				for row in rows:
					if row:
						rg_name = row[1]
						cost = row[0]
						self.cost_by_rg[rg_name] = {
							"currentMonth": cost,
							"subscription": subscription_id,
							"lastMonth": 0.
						}
			elif response.status_code == 401:
				logging.error("[Cost API][Current Month] Unauthorized Error for subscription {0}".format(subscription_id))
			else:
				logging.error("[Cost API][Current Month] Error code: {0}".format(response.status_code))
			logging.info("Done.")

		end = time.time()
		logging.info("Time to get RGs cost for Current Month: {0}".format(end - start))

	def get_cost_by_rg_last_month(self, headers=None):
		start = time.time()
		for subscription in self.CONFIG["AZURE_SUBSCRIPTIONS"]:
			subscription_id = subscription["ID"]
			logging.info("Getting last month RG cost for subscription {0}".format(subscription_id))
			url = self.CONFIG["URLS"]["COST_MGMT_BY_SUB"].format(SUBSCRIPTION_ID=subscription_id)
			logging.debug("url {0}".format(url))
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
					]
				},
				"timeframe":"TheLastmonth"
			}

			response = self.do_requests(url, COGSResourceManager.REQUESTS_POST, headers=headers, payload=request_body, content_type="json")

			if response.status_code == 200:
				data = json.loads(response.content)
				rows = data["properties"]["rows"]
				for row in rows:
					if row:
						rg_name = row[1]
						cost = row[0]
						if rg_name in self.cost_by_rg:
							self.cost_by_rg[rg_name]["lastMonth"] = cost
			elif response.status_code == 401:
				logging.error("[Cost API][Last Month] Unauthorized Error for subscription {0}".format(subscription_id))
			else:
				logging.error("[Cost API][Current Month] Error code: {0}".format(response.status_code))
			logging.info("Done.")
		
		end = time.time()
		logging.info("Time to get RGs cost for Last Month: {0}".format(end - start))


	def get_cost_by_rg_list(self):
		for rg_name, rg_values in self.cost_by_rg.items():
			self.cost_by_rg_list.append(
				(rg_name, rg_values["subscription"], rg_values["currentMonth"], rg_values["lastMonth"])
			)

	def get_cost_by_rg_owner(self):
		for owner, rg_info in self.rg_by_owner.items():
			for rg in rg_info["resource_groups"]:
				rg_name = rg["name"]
				
				if rg_name in self.cost_by_rg:
					cost = self.cost_by_rg[rg_name]
					rg["cost"] += cost

					rg_info["total_cost"] += cost

	def upsert_to_sql(self, tablename, data=None, is_update=False):
		sql_config = self.CONFIG["SQL"][tablename]
		logging.info("Upserting to table {0}".format(tablename))
		start = time.time()
		if not is_update:
			self.cursor.execute(sql_config["TRUNCATE_SQL"])
			self.cursor.executemany(sql_config["INSERT_SQL"], data)
		else:
			self.cursor.execute(sql_config["UPDATE_SQL"], data)
		self.cnxn.commit()
		end = time.time()
		logging.info("Time to upsert to table {0}: {1}".format(tablename, end - start))

	@staticmethod
	def get_filter(key, value, clause):
		return "{0} {1} '{2}'".format(key, clause, value)


	def get_all_resources_list_helper(self, headers=None, expand=None):
		resources_per_sub = self.get_resources_list(self.CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, expand=expand)
		for subscription_id, resources_list in resources_per_sub.items():
			for resource in resources_list:
				sku = resource["sku"] if "sku" in resource else None
				rg_name = resource["id"].split('/')[4]
				resource_provider = resource["type"].split('/')[0]
				created_time = datetime.strptime(resource["createdTime"][:23], self.CONFIG["DATES"]["READ_DATE_FORMAT"])
				self.resources_sql_list.append(
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

		return self.resources_sql_list

	def get_vmss_resource_list_helper(self, headers=None, expand=None):
		filter = self.get_filter("resourceType", "Microsoft.Compute/virtualMachineScaleSets", "eq")
		vmss_per_sub = self.get_resources_list(self.CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, filter=filter, expand=expand)
		for subscription_id, vmss_list in vmss_per_sub.items():
			for vmss in vmss_list:
				sku = vmss["sku"] if "sku" in vmss else None
				rg_name = vmss["id"].split('/')[4]
				created_time = datetime.strptime(vmss["createdTime"][:23], self.CONFIG["DATES"]["READ_DATE_FORMAT"])
				self.vmss_sql_list.append(
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

		return self.vmss_sql_list

	def get_apim_resource_list_helper(self, headers=None, expand=None):
		filter = self.get_filter("resourceType", "Microsoft.ApiManagement/service", "eq")
		apim_per_sub = self.get_resources_list(self.CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, filter=filter, expand=expand)
		for subscription_id, apim_list in apim_per_sub.items():
			for apim in apim_list:
				sku = apim["sku"] if "sku" in apim else None
				rg_name = apim["id"].split('/')[4]
				created_time = datetime.strptime(apim["createdTime"][:23], self.CONFIG["DATES"]["READ_DATE_FORMAT"])
				self.apim_sql_list.append(
					(
						subscription_id,
						rg_name,
						apim["name"],
						sku["capacity"] if sku and "capacity" in sku else None,
						created_time,
						sku["name"] if sku and "name" in sku else None
					)
				)

		return self.apim_sql_list

	def get_cosmos_resource_list_helper(self, headers=None, expand=None):
		filter = self.get_filter("resourceType", "Microsoft.DocumentDB/databaseAccounts", "eq")
		cosmos_per_sub = self.get_resources_list(self.CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, filter=filter, expand=expand)
		for subscription_id, cosmos_list in cosmos_per_sub.items():
			for cosmos in cosmos_list:
				rg_name = cosmos["id"].split('/')[4]
				created_time = datetime.strptime(cosmos["createdTime"][:23], self.CONFIG["DATES"]["READ_DATE_FORMAT"])
				changed_time = datetime.strptime(cosmos["changedTime"][:23], self.CONFIG["DATES"]["READ_DATE_FORMAT"])
				self.cosmos_sql_list.append(
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

		return self.cosmos_sql_list

	def get_sb_resource_list_helper(self, headers=None, expand=None):
		filter = self.get_filter("resourceType", "Microsoft.ServiceBus/namespaces", "eq")
		sb_per_sub = self.get_resources_list(self.CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, filter=filter, expand=expand)
		for subscription_id, sb_list in sb_per_sub.items():
			for sb in sb_list:
				sku = sb["sku"] if "sku" in sb else None
				rg_name = sb["id"].split('/')[4]
				created_time = datetime.strptime(sb["createdTime"][:23], self.CONFIG["DATES"]["READ_DATE_FORMAT"])
				changed_time = datetime.strptime(sb["changedTime"][:23], self.CONFIG["DATES"]["READ_DATE_FORMAT"])
				capacity = sku["capacity"] if sku and "capacity" in sku else None
				sku_name = sku["name"] if sku and "name" in sku else None
				tier = sku["tier"] if sku and "tier" in sku else None
				self.sb_sql_list.append(
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

		return self.sb_sql_list

	def _load_config(self):
		logging.info("Loading config...")
		script_dir = os.path.dirname(os.path.abspath(__file__))
		relative_path = "config\config.json"
		config_file_path = os.path.join(script_dir, relative_path)
		with open(config_file_path) as config_file:
			config_data = json.load(config_file)
		self.CONFIG = config_data
		logging.info("Done.")

	def _load_db_cnxn(self):
		logging.info("Loading DB connection...")
		db_config = self.CONFIG["DB"]
		db_connection_string = db_config["ODBC_CONNECTION_STR"].format(
				DRIVER=db_config["DRIVER"],
				DB_SERVER=db_config["SERVER_NAME"],
				DB_NAME=db_config["NAME"],
				DB_USERNAME=db_config["USERNAME"],
				DB_PWD=db_config["PWD"]
		)
		self.cnxn = pyodbc.connect(db_connection_string)
		self.cursor = self.cnxn.cursor()
		logging.info("Done.")

	def upsert_to_sql_wrapper(self):
		self.upsert_to_sql("RG", data=self.rg_list)
		self.upsert_to_sql("RG_COST", data=self.cost_by_rg_list)
		self.upsert_to_sql("ALL_RESOURCES", data=self.all_resources_list)
		self.upsert_to_sql("VMSS", data=self.vmss_list)
		self.upsert_to_sql("APIM", data=self.apim_list)
		self.upsert_to_sql("COSMOS", data=self.cosmos_list)
		self.upsert_to_sql("SERVICE_BUS", data=self.service_bus_list)
		self.upsert_to_sql("LAST_REFRESHED", data=datetime.now(), is_update=True)

	def build_resources_list_wrapper(self, headers=None, expand=None):
		self.vmss_list = self.get_vmss_resource_list_helper(headers=headers, expand=expand)
		self.apim_list = self.get_apim_resource_list_helper(headers=headers, expand=expand)
		self.cosmos_list = self.get_cosmos_resource_list_helper(headers=headers, expand=expand)
		self.service_bus_list = self.get_sb_resource_list_helper(headers=headers, expand=expand)
		self.all_resources_list = self.get_all_resources_list_helper(headers=headers, expand=expand)

	def get_resource_groups_list_wrapper(self, headers=None, expand=None):
		self.get_resource_groups_list(self.CONFIG["AZURE_SUBSCRIPTIONS"], headers=headers, filter=None, expand=expand)
		# get_tags_list(AZURE_SUBSCRIPTION_ID_1, headers=headers)
		# get_activity_logs_list(AZURE_SUBSCRIPTION_ID, headers=headers)
		self.get_resource_groups_by_owner()

	def get_cost_data_wrapper(self, headers=None):
		self.get_cost_by_rg_current_month(headers=headers)
		self.get_cost_by_rg_last_month(headers=headers)
		self.get_cost_by_rg_list()
		# get_cost_by_rg_owner()

	def print_orphan_rgs_older_than_n_days(self, days=1):
		self.print_list_of_orphan_rgs_older_than_n_days(days=days)


	def run(self):
		ACCESS_TOKEN = self._get_access_token()
		headers = {"Authorization": 'Bearer {0}'.format(ACCESS_TOKEN)}
		expand = "createdTime,changedTime"
		
		self.build_resources_list_wrapper(headers=headers, expand=expand)
		self.get_resource_groups_list_wrapper(headers=headers, expand=expand)
		self.get_cost_data_wrapper(headers=headers)

		self.upsert_to_sql_wrapper()


def main():
	resource_manager = COGSResourceManager()
	resource_manager.run()

	# resource_manager.print_orphan_rgs_older_than_n_days(days=14)

if __name__ == '__main__':
	logging.basicConfig(
		level=logging.DEBUG,
		format='[%(asctime)s] [%(levelname)8s] %(message)s',
		datefmt='%Y-%m-%d %H:%M:%S'
	)
	main()
