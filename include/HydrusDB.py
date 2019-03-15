import distutils.version
from . import HydrusConstants as HC
from . import HydrusData
from . import HydrusExceptions
from . import HydrusGlobals as HG
from . import HydrusPaths
from . import HydrusText
import os
import queue
import mysql.connector
from mysql.connector.constants import CharacterSet
import traceback
import time

CONNECTION_REFRESH_TIME = 60 * 30

def CanVacuum( db_path, stop_time = None ):
    return False
        
    
def ReadLargeIdQueryInSeparateChunks( cursor, select_statement, chunk_size ):
    
    table_name = 'mem.tempbigread' + os.urandom( 32 ).hex()
    
    cursor.execute( 'CREATE TABLE ' + table_name + ' ( temp_id INT AUTO_INCREMENT,  );' )
    
    cursor.execute( 'INSERT INTO ' + table_name + ' ( temp_id ) ' + select_statement ) # given statement should end in semicolon, so we are good
    
    finished = False
    
    while not finished:
        
        chunk = [ temp_id for ( temp_id, ) in cursor.execute( 'SELECT temp_id FROM ' + table_name + ' LIMIT ?;', ( chunk_size, ) ) ]
        
        if len( chunk ) == 0:
            
            finished = True
            
        else:
            
            cursor.executemany( 'DELETE FROM ' + table_name + ' WHERE temp_id = ?;', ( ( temp_id, ) for temp_id in chunk ) )
            
            yield chunk
            
        
    
    cursor.execute( 'DROP TABLE ' + table_name + ';' )
    
def VacuumDB( db_path ):
    pass
        

class HydrusDB( object ):
    
    READ_WRITE_ACTIONS = []
    UPDATE_WAIT = 2
    
    TRANSACTION_COMMIT_TIME = 120
    
    def __init__( self, controller, db_dir, db_name, no_wal = False ):
        
        self._controller = controller
        self._db_dir = db_dir
        self._db_name = db_name
        self._no_wal = no_wal
        
        self._transaction_started = 0
        self._transaction_contains_writes = False
        
        self._connection_timestamp = 0
        
        main_db_filename = db_name
            
        
        self._db_filenames = {}
        
        self._db_filenames[ 'main' ] = main_db_filename
        
        self._InitExternalDatabases()
            
        
        self._is_first_start = False
        self._is_db_updated = False
        self._local_shutdown = False
        self._loop_finished = False
        self._ready_to_serve_requests = False
        self._could_not_initialise = False
        
        self._jobs = queue.Queue()
        self._pubsubs = []
        
        self._currently_doing_job = False
        self._current_status = ''
        self._current_job_name = ''
        
        self._db = None
        self._c = None

        self._InitDB()
        
        self._RepairDB()

        self._c.execute('SELECT version FROM version;')
        ( version, ) = self._c.fetchone()
        
        if version > HC.SOFTWARE_VERSION:
            
            self._ReportOverupdatedDB( version )
            
        
        if version < HC.SOFTWARE_VERSION - 50:
            
            raise Exception( 'Your current database version of hydrus ' + str( version ) + ' is too old for this software version ' + str( HC.SOFTWARE_VERSION ) + ' to update. Please try updating with version ' + str( version + 45 ) + ' or earlier first.' )
            
        
        while version < HC.SOFTWARE_VERSION:
            
            time.sleep( self.UPDATE_WAIT )
            
            try:
                
                self._BeginImmediate()
                
            except Exception as e:
                
                raise HydrusExceptions.DBAccessException( str( e ) )
                
            
            try:
                
                self._UpdateDB( version )
                
                self._Commit()
                
                self._is_db_updated = True
                
            except:
                
                e = Exception( 'Updating the ' + self._db_name + ' db to version ' + str( version + 1 ) + ' caused this error:' + os.linesep + traceback.format_exc() )
                
                try:
                    
                    self._Rollback()
                    
                except Exception as rollback_e:
                    
                    HydrusData.Print( 'When the update failed, attempting to rollback the database failed.' )
                    
                    HydrusData.PrintException( rollback_e )
                    
                
                raise e

            self._c.execute('SELECT version FROM version;')
            ( version, ) = self._c.fetchone()
            
        
        self._CloseDBCursor()
        
        self._controller.CallToThreadLongRunning( self.MainLoop )
        
        while not self._ready_to_serve_requests:
            
            time.sleep( 0.1 )
            
            if self._could_not_initialise:
                
                raise Exception( 'Could not initialise the db! Error written to the log!' )
                
            
        
    
    def _AttachExternalDatabases( self ):
        pass
        
    
    def _BeginImmediate( self ):
        
        if not self._db.in_transaction:

            self._db.start_transaction()

            self._transaction_started = HydrusData.GetNow()
            self._transaction_contains_writes = False
            
        
    
    def _CleanUpCaches( self ):
        
        pass
        
    
    def _CloseDBCursor( self ):
        
        if self._db is not None:
            
            if self._db.in_transaction:
                
                self._Commit()

            self._c.close()
            self._c = None
            
        
    
    def _Commit( self ):
        
        if self._db.in_transaction:
            
            self._db.commit()

        else:
            
            HydrusData.Print( 'Received a call to commit, but was not in a transaction!' )
            
        
    
    def _CreateDB( self ):
        
        raise NotImplementedError()
        
    
    def _CreateIndex( self, table_name, columns, unique = False ):
        
        if '.' in table_name:
            
            table_name_simple = table_name.split( '.' )[1]
            
        else:
            
            table_name_simple = table_name

        index_name = table_name + '_' + '_'.join( columns ) + '_index'
        if len(index_name) > 64:
            index_name = "_".join(x[:4] for x in index_name.split("_"))

        if unique:
            
            create_phrase = 'CREATE UNIQUE INDEX '
            
        else:
            
            create_phrase = 'CREATE INDEX '
            
        
        on_phrase = ' ON ' + table_name_simple + ' (' + ', '.join( columns ) + ');'
        create_statement = create_phrase + index_name + on_phrase

        self._c.execute( create_statement )

    
    def _DisplayCatastrophicError( self, text ):
        
        message = 'The db encountered a serious error! This is going to be written to the log as well, but here it is for a screenshot:'
        message += os.linesep * 2
        message += text
        
        HydrusData.DebugPrint( message )
        
    
    def _GetRowCount( self ):
        
        row_count = self._c.rowcount
        
        if row_count == -1: return 0
        else: return row_count
        
    
    def _InitCaches( self ):
        
        pass
        
    
    def _InitDB( self ):

        
        self._InitDBCursor()
        
        self._c.execute( "SHOW DATABASES LIKE 'hydrus';"); result = self._c.fetchone()

        create_db = not result

        if create_db:
            
            self._is_first_start = True
            
            self._CreateDB()
            
            self._Commit()
            
            self._BeginImmediate()
        else:

            self._c.execute("USE hydrus;")
            
        
    
    def _InitDBCursor( self, started=False ):

        charset = CharacterSet.get_charset_info("utf8mb4", "utf8mb4_0900_ai_ci")

        if self._c:
            self._CloseDBCursor()

        if not started:
            self._db = mysql.connector.connect(
                host=HC.MYSQL_HOST,
                user=HC.MYSQL_USER,
                password=HC.MYSQL_PASSWORD,
                buffered=True,
                charset=charset[0]
            )
        elif not self._db:
            self._db = mysql.connector.connect(
                host=HC.MYSQL_HOST,
                user=HC.MYSQL_USER,
                password=HC.MYSQL_PASSWORD,
                database='hydrus',
                buffered=True,
                charset=charset[0]
            )
        
        self._connection_timestamp = HydrusData.GetNow()
        
        self._c = self._db.cursor()
        try:
            
            self._BeginImmediate()
            
        except Exception as e:
            
            raise HydrusExceptions.DBAccessException( str( e ) )
            
        
    
    def _InitDiskCache( self ):
        
        pass
        
    
    def _InitExternalDatabases( self ):
        
        pass
        
    
    def _ManageDBError( self, job, e ):
        
        raise NotImplementedError()
        
    
    def _ProcessJob( self, job ):
        
        job_type = job.GetType()
        
        ( action, args, kwargs ) = job.GetCallableTuple()
        
        try:
            
            if job_type in ( 'read_write', 'write' ):
                
                self._current_status = 'db writing'
                
                self._transaction_contains_writes = True
                
            else:
                
                self._current_status = 'db reading'
                
            
            self.publish_status_update()
            
            if job_type in ( 'read', 'read_write' ):
                
                result = self._Read( action, *args, **kwargs )
                
            elif job_type in ( 'write' ):
                
                result = self._Write( action, *args, **kwargs )
                
            
            if self._transaction_contains_writes and HydrusData.TimeHasPassed( self._transaction_started + self.TRANSACTION_COMMIT_TIME ):
                
                self._current_status = 'db committing'
                
                self.publish_status_update()
                
                self._Commit()
                
                self._BeginImmediate()
                
            else:
                
                self._Save()
                
            
            for ( topic, args, kwargs ) in self._pubsubs:
                
                self._controller.pub( topic, *args, **kwargs )
                
            
            if job.IsSynchronous():
                
                job.PutResult( result )
                
            
        except Exception as e:
            
            self._ManageDBError( job, e )
            
            try:
                
                self._Rollback()
                
            except Exception as rollback_e:
                
                HydrusData.Print( 'When the transaction failed, attempting to rollback the database failed. Please restart the client as soon as is convenient.' )

                self._CloseDBCursor()
                
                self._InitDBCursor(started=True)
                
                HydrusData.PrintException( rollback_e )
                
            
        finally:
            
            self._pubsubs = []
            
            self._current_status = ''
            
            self.publish_status_update()
            
        
    
    def _Read( self, action, *args, **kwargs ):
        
        raise NotImplementedError()
        
    
    def _RepairDB( self ):
        
        pass
        
    
    def _ReportOverupdatedDB( self, version ):
        
        pass
        
    
    def _ReportStatus( self, text ):
        
        HydrusData.Print( text )
        
    
    def _Rollback( self ):
        
        if self._db.in_transaction:
            
            self._db.rollback()
            
        else:
            
            HydrusData.Print( 'Received a call to rollback, but was not in a transaction!' )
            
        
    
    def _Save( self ):
        
        self._db.commit()
        self._db.start_transaction()
        
    
    def _SelectFromList( self, select_statement, xs ):
        
        # issue here is that doing a simple blah_id = ? is real quick and cacheable but doing a lot of fetchone()s is slow
        # blah_id IN ( 1, 2, 3 ) is fast to execute but not cacheable and doing the str() list splay takes time so there is initial lag
        # doing the temporaryintegertable trick works well for gigantic lists you refer to frequently but it is super laggy when you sometimes are only selecting four things
        # blah_id IN ( ?, ?, ? ) is fast and cacheable but there's a small limit (1024 is too many) to the number of params sql can handle
        # so lets do the latter but break it into 256-strong chunks to get a good medium
        
        # this will take a select statement with %s like so:
        # SELECT blah_id, blah FROM blahs WHERE blah_id IN %s;
        
        MAX_CHUNK_SIZE = 256
        
        # do this just so we aren't always reproducing this long string for gigantic lists
        # and also so we aren't overmaking it when this gets spammed with a lot of len() == 1 calls
        if len( xs ) >= MAX_CHUNK_SIZE:
            
            max_statement = select_statement % ( '(' + ','.join( ['%s'] * MAX_CHUNK_SIZE ) + ')' )
            
        
        for chunk in HydrusData.SplitListIntoChunks( xs, MAX_CHUNK_SIZE ):
            
            if len( chunk ) == MAX_CHUNK_SIZE:
                
                chunk_statement = max_statement
                
            else:
                
                chunk_statement = select_statement % ( '(' + ','.join( ['%s'] * len( chunk ) ) + ')' )

            self._c.execute(chunk_statement, chunk)
            for row in self._c.fetchall():
                
                yield row
                
            
        
    
    def _SelectFromListFetchAll( self, select_statement, xs ):
        
        return [ row for row in self._SelectFromList( select_statement, xs ) ]
        
    
    def _STI( self, iterable_cursor ):
        
        # strip singleton tuples to an iterator
        try:
            return ( item for ( item, ) in self._c.fetchall() )
        except mysql.connector.errors.InterfaceError:
            return ()
        
    
    def _STL( self, iterable_cursor ):
        
        # strip singleton tuples to a list
        try:
            return [ item for ( item, ) in self._c.fetchall() ]
        except mysql.connector.errors.InterfaceError:
            return []
        
    
    def _STS( self, iterable_cursor ):
        
        # strip singleton tuples to a set
        try:
            return { item for ( item, ) in self._c.fetchall()  }
        except mysql.connector.errors.InterfaceError:
            return {}
        
    
    def _UpdateDB( self, version ):
        
        raise NotImplementedError()
        
    
    def _Write( self, action, *args, **kwargs ):
        
        raise NotImplementedError()
        
    
    def pub_after_job( self, topic, *args, **kwargs ):
        
        if len( args ) == 0 and len( kwargs ) == 0:
            
            if ( topic, args, kwargs ) in self._pubsubs:
                
                return
                
            
        
        self._pubsubs.append( ( topic, args, kwargs ) )
        
    
    def publish_status_update( self ):
        
        pass
        
    
    def CurrentlyDoingJob( self ):
        
        return self._currently_doing_job
        
    
    def GetApproxTotalFileSize( self ):
        
        total = 0
        
        for filename in list(self._db_filenames.values()):
            
            path = os.path.join( self._db_dir, filename )
            
            total += os.path.getsize( path )
            
        
        return total
        
    
    def GetStatus( self ):
        
        return ( self._current_status, self._current_job_name )
        
    
    def IsDBUpdated( self ):
        
        return self._is_db_updated
        
    
    def IsFirstStart( self ):
        
        return self._is_first_start
        
    
    def LoopIsFinished( self ):
        
        return self._loop_finished
        
    
    def JobsQueueEmpty( self ):
        
        return self._jobs.empty()
        
    
    def MainLoop( self ):
        
        try:
            
            self._InitDBCursor(started=True) # have to reinitialise because the thread id has changed
            
            self._InitDiskCache()
            
            self._InitCaches()
            
        except:
            
            self._DisplayCatastrophicError( traceback.format_exc() )
            
            self._could_not_initialise = True
            
            return
            
        
        self._ready_to_serve_requests = True
        
        error_count = 0
        
        while not ( ( self._local_shutdown or self._controller.ModelIsShutdown() ) and self._jobs.empty() ):
            
            try:
                
                job = self._jobs.get( timeout = 1 )
                
                self._currently_doing_job = True
                self._current_job_name = job.ToString()
                
                self.publish_status_update()
                
                try:
                    
                    if HG.db_report_mode:
                        
                        summary = 'Running ' + job.ToString()
                        
                        HydrusData.ShowText( summary )
                        
                    
                    if HG.db_profile_mode:
                        
                        summary = 'Profiling ' + job.ToString()
                        
                        HydrusData.ShowText( summary )
                        
                        HydrusData.Profile( summary, 'self._ProcessJob( job )', globals(), locals() )
                        
                    else:
                        
                        self._ProcessJob( job )
                        
                    
                    error_count = 0
                    
                except:
                    
                    error_count += 1
                    
                    if error_count > 5:
                        
                        raise
                        
                    
                    self._jobs.put( job ) # couldn't lock db; put job back on queue
                    
                    time.sleep( 5 )
                    
                
                self._currently_doing_job = False
                self._current_job_name = ''
                
                self.publish_status_update()
                
            except queue.Empty:
                
                if self._transaction_contains_writes and HydrusData.TimeHasPassed( self._transaction_started + self.TRANSACTION_COMMIT_TIME ):
                    
                    self._Commit()
                    
                    self._BeginImmediate()
                    
                
            
            if HydrusData.TimeHasPassed( self._connection_timestamp + CONNECTION_REFRESH_TIME ): # just to clear out the journal files
                
                self._InitDBCursor(started=True)
                
            
        
        self._CleanUpCaches()
        
        self._CloseDBCursor()
        
        self._loop_finished = True
        
    
    def Read( self, action, *args, **kwargs ):
        
        if action in self.READ_WRITE_ACTIONS:
            
            job_type = 'read_write'
            
        else:
            
            job_type = 'read'
            
        
        synchronous = True
        
        job = HydrusData.JobDatabase( job_type, synchronous, action, *args, **kwargs )
        
        if self._controller.ModelIsShutdown():
            
            raise HydrusExceptions.ShutdownException( 'Application has shut down!' )
            
        
        self._jobs.put( job )
        
        return job.GetResult()
        
    
    def ReadyToServeRequests( self ):
        
        return self._ready_to_serve_requests
        
    
    def Shutdown( self ):
        
        self._local_shutdown = True
        
    
    def Write( self, action, synchronous, *args, **kwargs ):
        
        job_type = 'write'
        
        job = HydrusData.JobDatabase( job_type, synchronous, action, *args, **kwargs )
        
        if self._controller.ModelIsShutdown():
            
            raise HydrusExceptions.ShutdownException( 'Application has shut down!' )
            
        
        self._jobs.put( job )
        
        if synchronous: return job.GetResult()
        
    
class TemporaryIntegerTable( object ):
    
    def __init__( self, cursor, integer_iterable, column_name ):
        
        self._cursor = cursor
        self._integer_iterable = integer_iterable
        self._column_name = column_name
        
        self._table_name = 'mem.tempint' + os.urandom( 32 ).hex()
        
    
    def __enter__( self ):
        
        self._cursor.execute( 'CREATE TABLE ' + self._table_name + ' ( ' + self._column_name + ' INTEGER PRIMARY KEY );' )
        
        self._cursor.executemany( 'INSERT INTO ' + self._table_name + ' ( ' + self._column_name + ' ) VALUES ( ? );', ( ( i, ) for i in self._integer_iterable ) )
        
        return self._table_name
        
    
    def __exit__( self, exc_type, exc_val, exc_tb ):
        
        self._cursor.execute( 'DROP TABLE ' + self._table_name + ';' )
        
        return False
        
    
