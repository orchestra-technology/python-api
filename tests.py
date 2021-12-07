from api import Api


base_url = "https://trial.orchestra-technology.com"
proxy_addr = None


"""
Example: login.

api = Api(base_url, "api_user@orchestra-technology.com", api_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", proxy=proxy_addr)
api.login()

"""


"""
Example: create entity type.

task_id =  api.create_entity_type([{"name": "EntityTypeA", "help": "description"}])
api.polling_async_task(task_id)

"""


"""
Example: update entity type.

task_id = api.update_entity_type([{"name": "EntityTypeA", "help": "test description"}])
api.polling_async_task(task_id)

"""


"""
Example: update entity type.

data = api.read("EntityType", fields=["id"], filters=[["name", "is", "EntityTypeA"]], pages={"page":1, "page_size":1})
entity_type_id = data.get("id")
task_id = api.update_entity_type([{"id": entity_type_id, "help": "description"}])
api.polling_async_task(task_id)

"""


"""
Example: delete entity type.

data = api.read("EntityType", fields=["id"], filters=[["name", "is", "EntityTypeA"]], pages={"page":1, "page_size":1})
entity_type_id = data.get("id")
task_id = api.delete_entity_type([{"id": entity_type_id}])
api.polling_async_task(task_id)

"""


"""
Example: create field.

task_id = api.create_field([{"entity_type": "Task", "name": "text", "data_type": "text"}])
api.polling_async_task(task_id)

"""


"""
Example: update field.

task_id = api.update_field([{"entity_type": "Task", "name": "text", "help": "test modify help attribute."}])
api.polling_async_task(task_id)

"""


"""
Example: update field.

result = api.read("Field", ['id'], [['name', 'is', 'text'], ['entity_type__name', 'is', 'Task']], pages={"page":1, "page_size":1})
field_id = result.get("id")
task_id = api.delete_field([{"id": field_id}])
api.polling_async_task(task_id)

"""