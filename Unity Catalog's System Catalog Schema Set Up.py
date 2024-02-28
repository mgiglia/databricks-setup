# Databricks notebook source
# MAGIC %md
# MAGIC # United Catalog's System Catalog Schema Set Up
# MAGIC
# MAGIC There are several schemas that are available for monitoring your Databricks account, however these schemas need to be enabled by a user with account privlidges such as an admin.  
# MAGIC
# MAGIC Prerequites:  
# MAGIC
# MAGIC * At least one workspace that is set up with Unity Catalog for the account and the **Workspace ID** of one of those UC enabled workspaces.  This notebook should be run on one of those workspaces.  
# MAGIC * The user running this notebook must have a Databricks Personal Access Token (PAT) saved as a Databricks Secret for the particular workspace used.  The Databricks secret scope and the secret name for the PAT are inputted using Databricks text widgets.  
# MAGIC
# MAGIC ***

# COMMAND ----------

# MAGIC %md
# MAGIC ## Notebook Set Up

# COMMAND ----------

# MAGIC %md
# MAGIC #### Set Databricks Widgets for Required Inputs

# COMMAND ----------

# DBTITLE 1,Widgets Set Up
# Add a widget for the Databricks Secret Scope used for storing the user's Databricks Personal Access Token  
dbutils.widgets.text("pat_secret_scope", "credentials", "DB Secret Scope for PAT")

# Add a widget for the Databricks Secret representing the Databricks Personal Access Token  
dbutils.widgets.text("pat_secret", "databricks_pat", "DB Secret for PAT")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Databricks CLI Set Up and Configuration

# COMMAND ----------

# MAGIC %md
# MAGIC #### Install the Databricks CLI

# COMMAND ----------

# DBTITLE 1,Install the CLI
# install the Databricks CLI using a curl command and capture the response text
install_cmd_resp = !{"curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh"}
install_cmd_resp

# COMMAND ----------

# DBTITLE 1,Capture the CLI Path
# parse the installation command response to know where the CLI was installed.  This may be '/root/bin/databricks' or '/usr/local/bin/databricks'.  
cli_path = install_cmd_resp[0].split("at ")[1].replace(".", "")
cli_path

# COMMAND ----------

# MAGIC %md
# MAGIC #### Check the version of the Databricks CLI to ensure it installed correctly.  

# COMMAND ----------

# DBTITLE 1,Check CLI Version and Installation
version_cmd = f"{cli_path} -v"

!{version_cmd}

# COMMAND ----------

# MAGIC %md
# MAGIC #### Configure the Databricks CLI by passing in the full Workspace URL and the PAT
# MAGIC
# MAGIC The Workspace URL may be attained from the Databricks Spark Conf.  Note that its possible to return all of the values set in the Spark Conf as an array by running the following code:  
# MAGIC
# MAGIC > *spark_conf = spark.sparkContext.getConf()*  
# MAGIC > *spark_conf.getAll()*  
# MAGIC >   
# MAGIC
# MAGIC The Databricks Personal Access Token (PAT) will be retrieved using the Databricks Secrets Utility.  

# COMMAND ----------

# DBTITLE 1,Retrieve the Workspace URL and Personal Access Token
# return the workspace url from the Databricks Spark Conf
workspace_url = spark.conf.get("spark.databricks.workspaceUrl")

# retrieve the user's Databricks Personal Access Token
db_pat = dbutils.secrets.get(
  scope = dbutils.widgets.get("pat_secret_scope")
  ,key = dbutils.widgets.get("pat_secret")
)

print(f"""
  Workpace URL: {workspace_url}
  Databricks PAT: {db_pat}
""")

# COMMAND ----------

# DBTITLE 1,Configure the CLI
# configure the Databricks CLI on the cluster with the following command
configure_command = f"""echo '{db_pat}' | {cli_path} configure --host 'https://{workspace_url}'"""

!{configure_command}

# COMMAND ----------

# DBTITLE 1,Check Configuration
check_cli_cmd = f"{cli_path} current-user me"
!{check_cli_cmd}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Unity Catalog System Catalog Set Up

# COMMAND ----------

# MAGIC %md 
# MAGIC
# MAGIC #### Return the UC metastore summary to get the metastore ids.  

# COMMAND ----------

# DBTITLE 1,Metastore Summary

metastore_summary_cmd = f"{cli_path} metastores summary"

metastore_summary = !{metastore_summary_cmd } 
metastore_summary

# COMMAND ----------

# DBTITLE 1,Convert to JSON
# Convert metastore_summary string to JSON string
metastore_json_string = ''.join(metastore_summary)
metastore_json_string

# COMMAND ----------

# DBTITLE 1,Convert JSON to Spark Dataframe
# Create DataFrame with the json string
df = spark.read.json(spark.sparkContext.parallelize([metastore_json_string]))
display(df)

# COMMAND ----------

# DBTITLE 1,Return the Metastore IDs
metastore_ids = df.select("metastore_id").rdd.flatMap(lambda x: x).collect()
metastore_ids

# COMMAND ----------

# MAGIC %md
# MAGIC #### Check the status of the system catalog schemas for the metastore ids

# COMMAND ----------

# DBTITLE 1,Get the schema statuses for each metastore
system_schema_status = []
for metastore in metastore_ids:
  systemschemas_command = f"""curl -X GET -H "Authorization: Bearer {db_pat}" "https://{workspace_url}/api/2.0/unity-catalog/metastores/{metastore}/systemschemas" """
  status = !{systemschemas_command}
  status.append(metastore)
  system_schema_status += status

system_schema_status

# COMMAND ----------

# DBTITLE 1,Create a schema to load the schema statuses into a Spark Dataframe
from pyspark.sql.types import StructType, StructField, StringType, ArrayType, MapType

schema = StructType([
    StructField("col1", StringType(), True)
    ,StructField("col2", StringType(), True)
    ,StructField("col3", StringType(), True)
    ,StructField("col4", StringType(), True)
    ,StructField("col5", StringType(), True)
    ,StructField("col6", StringType(), True)
    ,StructField("schema_status", StringType(), True)
    ,StructField("metastore_id", StringType(), True)
])

# COMMAND ----------

# DBTITLE 1,Example JSON to learn the JSON scehma of the schema_status
sample_schema_status_json = """
{"schemas":[{"schema":"storage","state":"ENABLE_COMPLETED"},{"schema":"access","state":"ENABLE_COMPLETED"},{"schema":"billing","state":"ENABLE_COMPLETED"},{"schema":"compute","state":"ENABLE_COMPLETED"},{"schema":"marketplace","state":"ENABLE_COMPLETED"},{"schema":"operational_data","state":"UNAVAILABLE"},{"schema":"lineage","state":"ENABLE_COMPLETED"},{"schema":"information_schema","state":"ENABLE_COMPLETED"}]}
"""

# COMMAND ----------

# DBTITLE 1,Create the schema status dataframe
from pyspark.sql.functions import col, explode, from_json, schema_of_json

schema_status_df = (spark
  .createDataFrame(spark.sparkContext.parallelize([system_schema_status]), schema = schema)
  .withColumn("schema_status", from_json(col("schema_status"), schema=schema_of_json(sample_schema_status_json)))
  .withColumn("schemas", explode(col("schema_status.schemas")))
  .withColumn("schema", col("schemas.schema"))
  .withColumn("state", col("schemas.state"))
  .select("metastore_id", "schema", "state")

)

display(schema_status_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Enable Available System Catalog Schemas

# COMMAND ----------

# DBTITLE 1,Check for available system catalog scehmas to enable
available_to_enable = schema_status_df.filter(col("state") == "AVAILABLE").select("schema").rdd.flatMap(lambda x: x).collect()

available_to_enable

# COMMAND ----------

import requests

def enable_system_schema_func(metastore_id: str, schema: str, state: str, databricks_pat: str = db_pat, workspace_url: str = workspace_url) -> str:
  if state == "AVAILABLE":
    url = f"https://{workspace_url}/api/2.1/unity-catalog/metastores/{metastore_id}/systemschemas/{schema}"
    headers = {"Authorization": f"Bearer {databricks_pat}"}
    response = requests.put(url, headers=headers)
    return response
  
  

# COMMAND ----------

response = enable_system_schema_func(
  metastore_id = "fe90da00-0714-4d15-b3ed-60de3697184a"
  ,schema = "access"
  ,state = "AVAILABLE"
)

# COMMAND ----------

response.json()

# COMMAND ----------

# DBTITLE 1,Define enablement function as Spark UDF
from pyspark.sql.functions import pandas_udf
from pyspark.sql.functions import udf, udtf
from pyspark.sql.types import BooleanType
import requests

def enable_system_schema_func(metastore_id, schema, state, databricks_pat, workspace_url):
  if state == "AVAILABLE":
    requests.put(url = f"""/api/2.1/unity-catalog/metastores/{metastore_id}/systemschemas/{schema_name} """)
    enablement_cmd = f"""curl -v -X PUT -H "Authorization: Bearer {databricks_pat}" "https://{workspace_url}/api/2.0/unity-catalog/metastores/{metastore_id}/systemschemas/{schema}" """
    !{enablement_cmd}
    return True
  elif state == "ENABLE_COMPLETED":
    return True
  else:
    return False
  
enable_system_schema = pandas_udf(enable_system_schema_func, BooleanType())

# COMMAND ----------

schema_status_df.withColumn("enabled", enable_system_schema(col("metastore_id"), col("schema"), col("state"), db_pat, workspace_url))

# COMMAND ----------

for system_schema in available_to_enable:
  enablement_command = f"""curl -v -X PUT -H "Authorization: Bearer {db_pat}" "https://{workspace_url}/api/2.0/unity-catalog/metastores/{metastore}/systemschemas/{system_schema}" """
  !{enablement_command}

# COMMAND ----------

# MAGIC %sql 
# MAGIC
# MAGIC select * from system.access.audit