import mysql.connector
import yaml
import os
import glob


with open('config.yaml') as f:
    config = yaml.safe_load(f.read())

sql_conn = mysql.connector.connect(
                host=config['mysql_db']['host'],
                user=config['mysql_db']['user'],
                password=config['mysql_db']['password'],
                database=config['mysql_db']['database'],
                auth_plugin='mysql_native_password',
                buffered=True,
                allow_local_infile=True
            )
sql_cursor = sql_conn.cursor(buffered=True)
sql_cursor.execute('SET GLOBAL local_infile = true;')

template = "LOAD DATA LOCAL INFILE '%s' INTO TABLE %s FIELDS TERMINATED BY ',' ENCLOSED BY '%s' LINES TERMINATED BY '\\n' ignore 1 rows;"

for file in glob.iglob("E:\hydrus_backup\db\csv\*", recursive=True):
    if 'sqlite' in file or 'fts4' in file:
        continue

    table_name = os.path.basename(file.replace('main_', '')).split('.')[0]
    with open(file) as f:
        contents = f.read(150)

    type_one = '\'' in contents
    type_two = '"' in contents

    if not type_one and not type_two:
        print("-- " + file, str(0))
        print(template % (file.replace('\\','\\\\'), table_name, '"'))

    if type_one and not type_two:
        print("-- " + file, str(1))
        print(template % (file.replace('\\','\\\\'), table_name, '\'\''))

    if not type_one and type_two:
        print("-- " + file, str(2))
        print(template % (file.replace('\\','\\\\'), table_name, '"'))


    if type_one and type_two:
        print("-- " + file, str(12))
