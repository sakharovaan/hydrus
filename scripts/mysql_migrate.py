import mysql.connector
import binascii
import re
import yaml
import json
from os import path

bases = {
	'E:\hydrus_backup\db\ddl\client.sql': {},
	'E:\hydrus_backup\db\ddl\client.caches.sql': {},
    'E:\hydrus_backup\db\ddl\client.mappings.sql': {},
    'E:\hydrus_backup\db\ddl\client.master.sql': {}
}

with open('config.yaml') as f:
    config = yaml.safe_load(f.read())

sql_conn = mysql.connector.connect(
                host=config['mysql_db']['host'],
                user=config['mysql_db']['user'],
                password=config['mysql_db']['password'],
                buffered=True
            )
sql_cursor = sql_conn.cursor(buffered=True)
sql_cursor.execute('CREATE DATABASE IF NOT EXISTS ' + config['mysql_db']['database'] + ';')
sql_conn.commit()
sql_conn.close()

sql_conn = mysql.connector.connect(
                host=config['mysql_db']['host'],
                user=config['mysql_db']['user'],
                password=config['mysql_db']['password'],
                database=config['mysql_db']['database'],
                buffered=True
            )
sql_cursor = sql_conn.cursor(buffered=True)
sql_cursor.execute('SET autocommit=0;')
sql_cursor.execute('BEGIN;')



"self._c.execute( 'CREATE TABLE IF NOT EXISTS subtags_fts4 ( docid INT AUTO_INCREMENT PRIMARY KEY, subtag TEXT, FULLTEXT(subtag) );' )"


def adapt_line(line_bin):
    line = str(line_bin, 'utf8')

    if 'fts4' in line:
        return '-- ;'

    line =line.replace('\n','')

    if line.startswith('PRAGMA') or line.startswith('BEGIN TRANSACTION') or line.startswith('COMMIT') or line.startswith('ANALYZE'):
        return '-- ;'
    if line.startswith('CREATE TABLE'):
        if 'CREATE TABLE urls' in line:
            return 'CREATE TABLE IF NOT EXISTS urls ( url_id INTEGER PRIMARY KEY AUTO_INCREMENT, domain VARCHAR(255), url VARCHAR(2083) CHARACTER SET ascii UNIQUE ) ROW_FORMAT=COMPRESSED KEY_BLOCK_SIZE=8;'

        line = line.replace('AUTOINCREMENT', 'AUTO_INCREMENT')
        line = line.replace('BLOB_BYTES', 'VARCHAR(255)')
        line = line.replace('INTEGER_BOOLEAN', 'BOOL').replace('info INTEGER','info BIGINT')
        line = line.replace('TEXT_YAML', 'LONGTEXT').replace('TEXT PRIMARY KEY', 'varchar(255) PRIMARY KEY')
        line = line.replace('dictionary_string TEXT', 'dictionary_string LONGTEXT').replace('WITHOUT ROWID', '')

        line = line.replace('INTEGER PRIMARY KEY', 'INTEGER PRIMARY KEY AUTO_INCREMENT')
        line = line.replace('dump VARCHAR(255)', 'dump LONGTEXT').replace("'c0subtag'", "c0subtag varchar(255)")
        line = line.replace('dump_name TEXT', 'dump_name VARCHAR(255)').replace("TEXT UNIQUE", "varchar(255) UNIQUE")
        line = line.replace(';', 'ROW_FORMAT=COMPRESSED KEY_BLOCK_SIZE=8;')

    if line.startswith('INSERT INTO'):

        line = line.replace(",X'", ",'")
        line_bin = line_bin.replace(b",X'", b",'")

        if line.startswith("INSERT INTO json_dumps"):
            try:
                dump = re.search(r"(\[.*\])", line)[1]
                dump_json = dump.replace("'", "''")
                _ = json.loads(dump_json)
            except:
                dump = re.search(r"'([a-f0-9]*)'\);", line)[1]
                dump_json = binascii.a2b_hex(dump)
                line = line.replace(dump, str(dump_json.replace(b'\'', b'\'\''))[2:-1]).replace("\\'\\''", "\'\'")

        if line.startswith("INSERT INTO services"):
            return str(line_bin.replace(b'\\"', b'\\\\"'), 'utf8')


    if 'sqlite' in line:
        return '-- ;'

    return line

cur_line = 0
for file in bases.keys():
    print(file)
    try:
        with open(path.join(path.abspath('.'), file), 'rb') as f:
            cur_line = 0
            for line in f.readlines():
                if str(line, 'utf8').strip():
                    sql_cursor.execute(adapt_line(line))
                cur_line += 1
                if not cur_line % 10000:
                    print(file + ' ' +str(cur_line))
        
        
        sql_conn.commit()
    
    except Exception as e:
        print(e)
        print(cur_line)
        print(line)
