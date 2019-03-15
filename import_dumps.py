import mysql.connector
import uuid
import yaml
import json
import os
import glob

def _SaveNamedDump(dump):
    gen_uuid = str(uuid.uuid4())
    path = os.path.join('.', 'db', gen_uuid + '.json')

    with open(path, mode='w') as f:
        f.write(json.dumps(dump))

    return os.path.abspath(path)


with open('config.yaml') as f:
    config = yaml.safe_load(f.read())

sql_conn = mysql.connector.connect(
                host=config['mysql_db']['host'],
                user=config['mysql_db']['user'],
                password=config['mysql_db']['password'],
                database=config['mysql_db']['database'],
                buffered=True
            )
sql_cursor = sql_conn.cursor(buffered=True)

# with open('E:\\hydrus_backup\\db\\csv\\big\\json_dumps_named.csv') as f:
#     for line in f.readlines():
#         dump_type, dump_name, version, stamp, dump = line.split('В¤')
#         if dump.strip() != 'dump':
#             sql_cursor.execute('INSERT INTO json_dumps_named ( dump_type, dump_name, version, timestamp, dump ) VALUES ( %s, %s, %s, %s, %s );', ( dump_type, dump_name, version, stamp,  _SaveNamedDump(json.loads(dump))))
#             sql_conn.commit()
#
# with open('E:\\hydrus_backup\\db\\csv\\big\\json_dumps.csv') as f:
#     for line in f.readlines():
#         dump_type, version, dump = line.split('В¤')
#         if dump.strip() != 'dump':
#             sql_cursor.execute('INSERT INTO json_dumps ( dump_type, version, dump ) VALUES ( %s, %s, %s );', (  dump_type, version, _SaveNamedDump(json.loads(dump))))
#             sql_conn.commit()
dump_names = []
sql_cursor.execute('SELECT dump FROM json_dumps;')
result = sql_cursor.fetchall()
dump_names.extend([x[0] for x in result])
sql_cursor.execute('SELECT dump FROM json_dumps_named;')
result = sql_cursor.fetchall()
dump_names.extend([x[0] for x in result])

for file in glob.iglob(config['json_path'] + '*'):
    if os.path.split(file)[1].endswith('.json'):
        if not os.path.split(file)[1] in dump_names:
            os.unlink(file)
