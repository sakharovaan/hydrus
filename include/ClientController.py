import os
import wx

wx_first_num = int( wx.__version__[0] )

if wx_first_num < 4:
    
    wx_error = 'Unfortunately, hydrus now requires the new Phoenix (4.x) version of wx.'
    wx_error += os.linesep * 2
    wx_error += 'Please check the \'running from source\' page in the html help for more details.'
    
    raise Exception( wx_error )
    
from . import ClientCaches
from . import ClientData
from . import ClientDaemons
from . import ClientDefaults
from . import ClientGUICommon
from . import ClientGUIMenus
from . import ClientNetworking
from . import ClientNetworkingBandwidth
from . import ClientNetworkingDomain
from . import ClientNetworkingLogin
from . import ClientNetworkingSessions
from . import ClientOptions
from . import ClientPaths
from . import ClientThreading
import hashlib
from . import HydrusConstants as HC
from . import HydrusController
from . import HydrusData
from . import HydrusExceptions
from . import HydrusGlobals as HG
from . import HydrusNetworking
from . import HydrusPaths
from . import HydrusSerialisable
from . import HydrusThreading
from . import HydrusVideoHandling
from . import ClientConstants as CC
from . import ClientDB
from . import ClientGUI
from . import ClientGUIDialogs
from . import ClientGUIScrolledPanelsManagement
from . import ClientGUITopLevelWindows
import gc
import psutil
import threading
import time
import traceback

if not HG.twisted_is_broke:
    
    from twisted.internet import reactor, defer
    
class Controller( HydrusController.HydrusController ):
    
    def __init__( self, db_dir, no_daemons, no_wal ):
        
        self._last_shutdown_was_bad = False
        
        self._is_booted = False
        
        self._splash = None
        
        HydrusController.HydrusController.__init__( self, db_dir, no_daemons, no_wal )
        
        self._name = 'client'
        
        HG.client_controller = self
        
        # just to set up some defaults, in case some db update expects something for an odd yaml-loading reason
        self.options = ClientDefaults.GetClientDefaultOptions()
        self.new_options = ClientOptions.ClientOptions( self.db_dir )
        
        HC.options = self.options
        
        self._page_key_lock = threading.Lock()
        
        self._alive_page_keys = set()
        self._closed_page_keys = set()
        
        self._last_mouse_position = None
        self._menu_open = False
        self._previously_idle = False
        self._idle_started = None
        
        self.client_files_manager = None
        self.services_manager = None
        
    
    def _InitDB( self ):
        
        return ClientDB.DB( self, self.db_dir, 'client', no_wal = self._no_wal )
        
    
    def _InitTempDir( self ):
        
        self.temp_dir = ClientPaths.GetTempDir()
        
    
    def _DestroySplash( self ):
        
        if self._splash is not None:
            
            self._splash.DestroyLater()
            
            self._splash = None
            
        
    
    def _ReportShutdownDaemonsStatus( self ):
        
        names = { daemon.name for daemon in self._daemons if daemon.is_alive() }
        
        names = list( names )
        
        names.sort()
        
        self.pub( 'splash_set_status_subtext', ', '.join( names ) )
        
    
    def AcquirePageKey( self ):
        
        with self._page_key_lock:
            
            page_key = HydrusData.GenerateKey()
            
            self._alive_page_keys.add( page_key )
            
            return page_key
            
        
    
    def CallBlockingToWx( self, func, *args, **kwargs ):
        
        def wx_code( job_key ):
            
            try:
                
                result = func( *args, **kwargs )
                
                job_key.SetVariable( 'result', result )
                
            except HydrusExceptions.PermissionException as e:
                
                job_key.SetVariable( 'error', e )
                
            except Exception as e:
                
                job_key.SetVariable( 'error', e )
                
                HydrusData.Print( 'CallBlockingToWx just caught this error:' )
                HydrusData.DebugPrint( traceback.format_exc() )
                
            finally:
                
                job_key.Finish()
                
            
        
        job_key = ClientThreading.JobKey()
        
        job_key.Begin()
        
        wx.CallAfter( wx_code, job_key )
        
        while not job_key.IsDone():
            
            if self._model_shutdown:
                
                raise HydrusExceptions.ShutdownException( 'Application is shutting down!' )
                
            
            time.sleep( 0.05 )
            
        
        if job_key.HasVariable( 'result' ):
            
            # result can be None, for wx_code that has no return variable
            
            result = job_key.GetIfHasVariable( 'result' )
            
            return result
            
        
        error = job_key.GetIfHasVariable( 'error' )
        
        if error is not None:
            
            raise error
            
        
        raise HydrusExceptions.ShutdownException()
        
    
    def CallLaterWXSafe( self, window, initial_delay, func, *args, **kwargs ):
        
        job_scheduler = self._GetAppropriateJobScheduler( initial_delay )
        
        call = HydrusData.Call( func, *args, **kwargs )
        
        job = ClientThreading.WXAwareJob( self, job_scheduler, window, initial_delay, call )
        
        job_scheduler.AddJob( job )
        
        return job
        
    
    def CallRepeatingWXSafe( self, window, initial_delay, period, func, *args, **kwargs ):
        
        job_scheduler = self._GetAppropriateJobScheduler( period )
        
        call = HydrusData.Call( func, *args, **kwargs )
        
        job = ClientThreading.WXAwareRepeatingJob( self, job_scheduler, window, initial_delay, period, call )
        
        job_scheduler.AddJob( job )
        
        return job
        
    
    def CheckAlreadyRunning( self ):
    
        while HydrusData.IsAlreadyRunning( self.db_dir, 'client' ):
            
            self.pub( 'splash_set_status_text', 'client already running' )
            
            def wx_code():
                
                message = 'It looks like another instance of this client is already running, so this instance cannot start.'
                message += os.linesep * 2
                message += 'If the old instance is closing and does not quit for a _very_ long time, it is usually safe to force-close it from task manager.'
                
                with ClientGUIDialogs.DialogYesNo( self._splash, message, 'The client is already running.', yes_label = 'wait a bit, then try again', no_label = 'forget it' ) as dlg:
                    
                    if dlg.ShowModal() != wx.ID_YES:
                        
                        raise HydrusExceptions.PermissionException()
                        
                    
                
            
            self.CallBlockingToWx( wx_code )
            
            for i in range( 10, 0, -1 ):
                
                if not HydrusData.IsAlreadyRunning( self.db_dir, 'client' ):
                    
                    break
                    
                
                self.pub( 'splash_set_status_text', 'waiting ' + str( i ) + ' seconds' )
                
                time.sleep( 1 )
                
            
        
    
    def CheckMouseIdle( self ):
        
        mouse_position = wx.GetMousePosition()
        
        if self._last_mouse_position is None:
            
            self._last_mouse_position = mouse_position
            
        elif mouse_position != self._last_mouse_position:
            
            idle_before_position_update = self.CurrentlyIdle()
            
            self._timestamps[ 'last_mouse_action' ] = HydrusData.GetNow()
            
            self._last_mouse_position = mouse_position
            
            idle_after_position_update = self.CurrentlyIdle()
            
            move_knocked_us_out_of_idle = ( not idle_before_position_update ) and idle_after_position_update
            
            if move_knocked_us_out_of_idle:
                
                self.pub( 'set_status_bar_dirty' )
                
            
        
    
    def ClosePageKeys( self, page_keys ):
        
        with self._page_key_lock:
            
            self._closed_page_keys.update( page_keys )
            
        
    
    def CreateSplash( self ):
        
        try:
            
            self._splash = ClientGUI.FrameSplash( self )
            
        except:
            
            HydrusData.Print( 'There was an error trying to start the splash screen!' )
            
            HydrusData.Print( traceback.format_exc() )
            
            raise
            
        
    
    def CurrentlyIdle( self ):
        
        if HG.force_idle_mode:
            
            self._idle_started = 0
            
            return True
            
        
        if not HydrusData.TimeHasPassed( self._timestamps[ 'boot' ] + 120 ):
            
            return False
            
        
        idle_normal = self.options[ 'idle_normal' ]
        idle_period = self.options[ 'idle_period' ]
        idle_mouse_period = self.options[ 'idle_mouse_period' ]
        
        if idle_normal:
            
            currently_idle = True
            
            if idle_period is not None:
                
                if not HydrusData.TimeHasPassed( self._timestamps[ 'last_user_action' ] + idle_period ):
                    
                    currently_idle = False
                    
                
            
            if idle_mouse_period is not None:
                
                if not HydrusData.TimeHasPassed( self._timestamps[ 'last_mouse_action' ] + idle_mouse_period ):
                    
                    currently_idle = False
                    
                
            
        else:
            
            currently_idle = False
            
        
        turning_idle = currently_idle and not self._previously_idle
        
        self._previously_idle = currently_idle
        
        if turning_idle:
            
            self._idle_started = HydrusData.GetNow()
            
            self.pub( 'wake_daemons' )
            
        
        if not currently_idle:
            
            self._idle_started = None
            
        
        return currently_idle
        
    
    def CurrentlyVeryIdle( self ):
        
        if self._idle_started is not None and HydrusData.TimeHasPassed( self._idle_started + 3600 ):
            
            return True
            
        
        return False
        
    
    def DoIdleShutdownWork( self ):
        
        stop_time = HydrusData.GetNow() + ( self.options[ 'idle_shutdown_max_minutes' ] * 60 )
        
        self.MaintainDB( stop_time = stop_time )
        
        if not self.options[ 'pause_repo_sync' ]:
            
            services = self.services_manager.GetServices( HC.REPOSITORIES )
            
            for service in services:
                
                if HydrusData.TimeHasPassed( stop_time ):
                    
                    return
                    
                
                service.SyncProcessUpdates( only_when_idle = False, stop_time = stop_time )
                
            
        
        self.Write( 'last_shutdown_work_time', HydrusData.GetNow() )
        
    
    def Exit( self ):
        
        if HG.emergency_exit:
            
            self.ShutdownView()
            self.ShutdownModel()
            
            HydrusData.CleanRunningFile( self.db_dir, 'client' )
            
        else:
            
            try:
                
                last_shutdown_work_time = self.Read( 'last_shutdown_work_time' )
                
                shutdown_work_period = self.new_options.GetInteger( 'shutdown_work_period' )
                
                we_can_shutdown_work = HydrusData.TimeHasPassed( last_shutdown_work_time + shutdown_work_period )
                
                idle_shutdown_action = self.options[ 'idle_shutdown' ]
                
                if we_can_shutdown_work and idle_shutdown_action in ( CC.IDLE_ON_SHUTDOWN, CC.IDLE_ON_SHUTDOWN_ASK_FIRST ):
                    
                    idle_shutdown_max_minutes = self.options[ 'idle_shutdown_max_minutes' ]
                    
                    time_to_stop = HydrusData.GetNow() + ( idle_shutdown_max_minutes * 60 )
                    
                    work_to_do = self.GetIdleShutdownWorkDue( time_to_stop )
                    
                    if len( work_to_do ) > 0:
                        
                        if idle_shutdown_action == CC.IDLE_ON_SHUTDOWN_ASK_FIRST:
                            
                            text = 'Is now a good time for the client to do up to ' + HydrusData.ToHumanInt( idle_shutdown_max_minutes ) + ' minutes\' maintenance work? (Will auto-no in 15 seconds)'
                            text += os.linesep * 2
                            text += 'The outstanding jobs appear to be:'
                            text += os.linesep * 2
                            text += os.linesep.join( work_to_do )
                            
                            with ClientGUIDialogs.DialogYesNo( self._splash, text, title = 'Maintenance is due' ) as dlg_yn:
                                
                                job = self.CallLaterWXSafe( dlg_yn, 15, dlg_yn.EndModal, wx.ID_NO )
                                
                                try:
                                    
                                    if dlg_yn.ShowModal() == wx.ID_YES:
                                        
                                        HG.do_idle_shutdown_work = True
                                        
                                    else:
                                        
                                        self.Write( 'last_shutdown_work_time', HydrusData.GetNow() )
                                        
                                    
                                finally:
                                    
                                    job.Cancel()
                                    
                                
                            
                        else:
                            
                            HG.do_idle_shutdown_work = True
                            
                        
                    
                
                self.CallToThreadLongRunning( self.THREADExitEverything )
                
            except:
                
                self._DestroySplash()
                
                HydrusData.DebugPrint( traceback.format_exc() )
                
                HG.emergency_exit = True
                
                self.Exit()
                
            
        
    
    def GetApp( self ):
        
        return self._app
        
    
    def GetBandwidthManager( self ):
        
        raise NotImplementedError()
        
    
    def GetClipboardText( self ):
        
        if wx.TheClipboard.Open():
            
            data = wx.TextDataObject()
            
            wx.TheClipboard.GetData( data )
            
            wx.TheClipboard.Close()
            
            text = data.GetText()
            
            return text
            
        else:
            
            raise Exception( 'I could not get permission to access the clipboard.' )
            
        
    
    def GetCommandFromShortcut( self, shortcut_names, shortcut ):
        
        return self._shortcuts_manager.GetCommand( shortcut_names, shortcut )
        
    
    def GetGUI( self ):
        
        return self.gui
        
    
    def GetIdleShutdownWorkDue( self, time_to_stop ):
        
        work_to_do = []
        
        work_to_do.extend( self.Read( 'maintenance_due', time_to_stop ) )
        
        services = self.services_manager.GetServices( HC.REPOSITORIES )
        
        for service in services:
            
            if service.CanDoIdleShutdownWork():
                
                work_to_do.append( service.GetName() + ' repository processing' )
                
            
        
        return work_to_do
        
    
    def GetNewOptions( self ):
        
        return self.new_options
        
    
    def InitClientFilesManager( self ):
        
        def wx_code( missing_locations ):
            
            with ClientGUITopLevelWindows.DialogManage( None, 'repair file system' ) as dlg:
                
                panel = ClientGUIScrolledPanelsManagement.RepairFileSystemPanel( dlg, missing_locations )
                
                dlg.SetPanel( panel )
                
                if dlg.ShowModal() == wx.ID_OK:
                    
                    self.client_files_manager = ClientCaches.ClientFilesManager( self )
                    
                    missing_locations = self.client_files_manager.GetMissing()
                    
                else:
                    
                    raise HydrusExceptions.PermissionException( 'File system failed, user chose to quit.' )
                    
                
            
            return missing_locations
            
        
        self.client_files_manager = ClientCaches.ClientFilesManager( self )
        
        missing_locations = self.client_files_manager.GetMissing()
        
        while len( missing_locations ) > 0:
            
            missing_locations = self.CallBlockingToWx( wx_code, missing_locations )
            
        
    
    def InitModel( self ):
        
        self.pub( 'splash_set_title_text', 'booting db\u2026' )
        
        HydrusController.HydrusController.InitModel( self )
        
        self.pub( 'splash_set_status_text', 'initialising managers' )
        
        self.pub( 'splash_set_status_subtext', 'services' )
        
        self.services_manager = ClientCaches.ServicesManager( self )
        
        self.pub( 'splash_set_status_subtext', 'options' )
        
        self.options = self.Read( 'options' )
        self.new_options = self.Read( 'serialisable', HydrusSerialisable.SERIALISABLE_TYPE_CLIENT_OPTIONS )
        
        HC.options = self.options
        
        if self.new_options.GetBoolean( 'use_system_ffmpeg' ):
            
            if HydrusVideoHandling.FFMPEG_PATH.startswith( HC.BIN_DIR ):
                
                HydrusVideoHandling.FFMPEG_PATH = os.path.basename( HydrusVideoHandling.FFMPEG_PATH )
                
            
        
        self.pub( 'splash_set_status_subtext', 'client files' )
        
        self.InitClientFilesManager()
        
        #
        
        self.pub( 'splash_set_status_subtext', 'network' )
        
        self.parsing_cache = ClientCaches.ParsingCache()
        
        bandwidth_manager = self.Read( 'serialisable', HydrusSerialisable.SERIALISABLE_TYPE_NETWORK_BANDWIDTH_MANAGER )
        
        if bandwidth_manager is None:
            
            bandwidth_manager = ClientNetworkingBandwidth.NetworkBandwidthManager()
            
            ClientDefaults.SetDefaultBandwidthManagerRules( bandwidth_manager )
            
            bandwidth_manager._dirty = True
            
            wx.MessageBox( 'Your bandwidth manager was missing on boot! I have recreated a new empty one with default rules. Please check that your hard drive and client are ok and let the hydrus dev know the details if there is a mystery.' )
            
        
        session_manager = self.Read( 'serialisable', HydrusSerialisable.SERIALISABLE_TYPE_NETWORK_SESSION_MANAGER )
        
        if session_manager is None:
            
            session_manager = ClientNetworkingSessions.NetworkSessionManager()
            
            session_manager._dirty = True
            
            wx.MessageBox( 'Your session manager was missing on boot! I have recreated a new empty one. Please check that your hard drive and client are ok and let the hydrus dev know the details if there is a mystery.' )
            
        
        domain_manager = self.Read( 'serialisable', HydrusSerialisable.SERIALISABLE_TYPE_NETWORK_DOMAIN_MANAGER )
        
        if domain_manager is None:
            
            domain_manager = ClientNetworkingDomain.NetworkDomainManager()
            
            ClientDefaults.SetDefaultDomainManagerData( domain_manager )
            
            domain_manager._dirty = True
            
            wx.MessageBox( 'Your domain manager was missing on boot! I have recreated a new empty one. Please check that your hard drive and client are ok and let the hydrus dev know the details if there is a mystery.' )
            
        
        domain_manager.Initialise()
        
        login_manager = self.Read( 'serialisable', HydrusSerialisable.SERIALISABLE_TYPE_NETWORK_LOGIN_MANAGER )
        
        if login_manager is None:
            
            login_manager = ClientNetworkingLogin.NetworkLoginManager()
            
            ClientDefaults.SetDefaultLoginManagerScripts( login_manager )
            
            login_manager._dirty = True
            
            wx.MessageBox( 'Your login manager was missing on boot! I have recreated a new empty one. Please check that your hard drive and client are ok and let the hydrus dev know the details if there is a mystery.' )
            
        
        login_manager.Initialise()
        
        self.network_engine = ClientNetworking.NetworkEngine( self, bandwidth_manager, session_manager, domain_manager, login_manager )
        
        self.CallToThreadLongRunning( self.network_engine.MainLoop )
        
        #
        
        self._shortcuts_manager = ClientCaches.ShortcutsManager( self )
        
        self.local_booru_manager = ClientCaches.LocalBooruCache( self )
        
        self.file_viewing_stats_manager = ClientCaches.FileViewingStatsManager( self )
        
        self.pub( 'splash_set_status_subtext', 'tag censorship' )
        
        self._managers[ 'tag_censorship' ] = ClientCaches.TagCensorshipManager( self )
        
        self.pub( 'splash_set_status_subtext', 'tag siblings' )
        
        self._managers[ 'tag_siblings' ] = ClientCaches.TagSiblingsManager( self )
        
        self.pub( 'splash_set_status_subtext', 'tag parents' )
        
        self._managers[ 'tag_parents' ] = ClientCaches.TagParentsManager( self )
        self._managers[ 'undo' ] = ClientCaches.UndoManager( self )
        
        def wx_code():
            
            self._caches[ 'images' ] = ClientCaches.RenderedImageCache( self )
            self._caches[ 'thumbnail' ] = ClientCaches.ThumbnailCache( self )
            self.bitmap_manager = ClientCaches.BitmapManager( self )
            
            CC.GlobalBMPs.STATICInitialise()
            
        
        self.pub( 'splash_set_status_subtext', 'image caches' )
        
        self.CallBlockingToWx( wx_code )
        
        self.sub( self, 'ToClipboard', 'clipboard' )
        self.sub( self, 'RestartBooru', 'restart_booru' )
        
    
    def InitView( self ):
        
        if self.options[ 'password' ] is not None:
            
            self.pub( 'splash_set_status_text', 'waiting for password' )
            
            def wx_code_password():
                
                while True:
                    
                    with wx.PasswordEntryDialog( self._splash, 'Enter your password', 'Enter password' ) as dlg:
                        
                        if dlg.ShowModal() == wx.ID_OK:
                            
                            password_bytes = bytes( dlg.GetValue(), 'utf-8' )
                            
                            if hashlib.sha256( password_bytes ).digest() == self.options[ 'password' ]:
                                
                                break
                                
                            elif HC.SOFTWARE_VERSION == 335:
                                
                                wx.MessageBox( 'The password you entered was incorrect! This _may_ be a result of the py3 update, so you are forgiven for this version. Please try remaking your password and testing it works in a normal boot in this version. Report continued errors to hydrus dev please!' )
                                
                                break
                                
                            
                        else:
                            
                            raise HydrusExceptions.PermissionException( 'Bad password check' )
                            
                        
                    
                
            
            self.CallBlockingToWx( wx_code_password )
            
        
        self.pub( 'splash_set_title_text', 'booting gui\u2026' )
        
        def wx_code_gui():
            
            self.gui = ClientGUI.FrameGUI( self )
            
            self.ResetIdleTimer()
            
        
        self.CallBlockingToWx( wx_code_gui )
        
        # ShowText will now popup as a message, as popup message manager has overwritten the hooks
        
        HydrusController.HydrusController.InitView( self )
        
        self._booru_port_connection = None
        
        self.RestartBooru()
        
        if not self._no_daemons:
            
            self._daemons.append( HydrusThreading.DAEMONWorker( self, 'SynchroniseAccounts', ClientDaemons.DAEMONSynchroniseAccounts, ( 'notify_unknown_accounts', ) ) )
            self._daemons.append( HydrusThreading.DAEMONWorker( self, 'SaveDirtyObjects', ClientDaemons.DAEMONSaveDirtyObjects, ( 'important_dirt_to_clean', ), period = 30 ) )
            
            self._daemons.append( HydrusThreading.DAEMONForegroundWorker( self, 'DownloadFiles', ClientDaemons.DAEMONDownloadFiles, ( 'notify_new_downloads', 'notify_new_permissions' ) ) )
            self._daemons.append( HydrusThreading.DAEMONForegroundWorker( self, 'SynchroniseSubscriptions', ClientDaemons.DAEMONSynchroniseSubscriptions, ( 'notify_restart_subs_sync_daemon', 'notify_new_subscriptions' ), period = 4 * 3600, init_wait = 60, pre_call_wait = 3 ) )
            self._daemons.append( HydrusThreading.DAEMONForegroundWorker( self, 'CheckImportFolders', ClientDaemons.DAEMONCheckImportFolders, ( 'notify_restart_import_folders_daemon', 'notify_new_import_folders' ), period = 180 ) )
            self._daemons.append( HydrusThreading.DAEMONForegroundWorker( self, 'CheckExportFolders', ClientDaemons.DAEMONCheckExportFolders, ( 'notify_restart_export_folders_daemon', 'notify_new_export_folders' ), period = 180 ) )
            self._daemons.append( HydrusThreading.DAEMONForegroundWorker( self, 'MaintainTrash', ClientDaemons.DAEMONMaintainTrash, init_wait = 120 ) )
            self._daemons.append( HydrusThreading.DAEMONForegroundWorker( self, 'SynchroniseRepositories', ClientDaemons.DAEMONSynchroniseRepositories, ( 'notify_restart_repo_sync_daemon', 'notify_new_permissions' ), period = 4 * 3600, pre_call_wait = 1 ) )
            
            self._daemons.append( HydrusThreading.DAEMONBackgroundWorker( self, 'UPnP', ClientDaemons.DAEMONUPnP, ( 'notify_new_upnp_mappings', ), init_wait = 120, pre_call_wait = 6 ) )
            
        
        self.CallRepeatingWXSafe( self, 10.0, 10.0, self.CheckMouseIdle )
        
        if self.db.IsFirstStart():
            
            message = 'Hi, this looks like the first time you have started the hydrus client.'
            message += os.linesep * 2
            message += 'Don\'t forget to check out the help if you haven\'t already--it has an extensive \'getting started\' section.'
            message += os.linesep * 2
            message += 'To dismiss popup messages like this, right-click them.'
            
            HydrusData.ShowText( message )
            
        
        if self.db.IsDBUpdated():
            
            HydrusData.ShowText( 'The client has updated to version ' + str( HC.SOFTWARE_VERSION ) + '!' )
            
        
        for message in self.db.GetInitialMessages():
            
            HydrusData.ShowText( message )
            
        
    
    def IsBooted( self ):
        
        return self._is_booted
        
    
    def LastShutdownWasBad( self ):
        
        return self._last_shutdown_was_bad
        
    
    def MaintainDB( self, stop_time = None ):
        
        if self.new_options.GetBoolean( 'maintain_similar_files_duplicate_pairs_during_idle' ):
            
            phashes_stop_time = stop_time
            
            if phashes_stop_time is None:
                
                phashes_stop_time = HydrusData.GetNow() + 15
                
            
            self.WriteSynchronous( 'maintain_similar_files_phashes', stop_time = phashes_stop_time )
            
            tree_stop_time = stop_time
            
            if tree_stop_time is None:
                
                tree_stop_time = HydrusData.GetNow() + 30
                
            
            self.WriteSynchronous( 'maintain_similar_files_tree', stop_time = tree_stop_time, abandon_if_other_work_to_do = True )
            
            search_distance = self.new_options.GetInteger( 'similar_files_duplicate_pairs_search_distance' )
            
            search_stop_time = stop_time
            
            if search_stop_time is None:
                
                search_stop_time = HydrusData.GetNow() + 60
                
            
            self.WriteSynchronous( 'maintain_similar_files_duplicate_pairs', search_distance, stop_time = search_stop_time, abandon_if_other_work_to_do = True )
            
        
        if stop_time is None or not HydrusData.TimeHasPassed( stop_time ):
            
            self.WriteSynchronous( 'maintain_file_reparsing', stop_time = stop_time )
            
        
        if stop_time is None or not HydrusData.TimeHasPassed( stop_time ):
            
            self.WriteSynchronous( 'vacuum', stop_time = stop_time )
            
        
        if stop_time is None or not HydrusData.TimeHasPassed( stop_time ):
            
            self.WriteSynchronous( 'analyze', stop_time = stop_time )
            
        
        if stop_time is None or not HydrusData.TimeHasPassed( stop_time ):
            
            if HydrusData.TimeHasPassed( self._timestamps[ 'last_service_info_cache_fatten' ] + ( 60 * 20 ) ):
                
                self.pub( 'splash_set_status_text', 'fattening service info' )
                
                services = self.services_manager.GetServices()
                
                for service in services:
                    
                    self.pub( 'splash_set_status_subtext', service.GetName() )
                    
                    try: self.Read( 'service_info', service.GetServiceKey() )
                    except: pass # sometimes this breaks when a service has just been removed and the client is closing, so ignore the error
                    
                
                self._timestamps[ 'last_service_info_cache_fatten' ] = HydrusData.GetNow()
                
            
        
    
    def MaintainMemoryFast( self ):
        
        HydrusController.HydrusController.MaintainMemoryFast( self )
        
        self.parsing_cache.CleanCache()
        
    
    def MaintainMemorySlow( self ):
        
        HydrusController.HydrusController.MaintainMemorySlow( self )
        
        if HydrusData.TimeHasPassed( self._timestamps[ 'last_page_change' ] + 30 * 60 ):
            
            self.pub( 'delete_old_closed_pages' )
            
            self._timestamps[ 'last_page_change' ] = HydrusData.GetNow()
            
        
        disk_cache_maintenance_mb = self.new_options.GetNoneableInteger( 'disk_cache_maintenance_mb' )
        
        if disk_cache_maintenance_mb is not None:
            
            if self.CurrentlyVeryIdle():
                
                cache_period = 3600
                disk_cache_stop_time = HydrusData.GetNow() + 30
                
            elif self.CurrentlyIdle():
                
                cache_period = 1800
                disk_cache_stop_time = HydrusData.GetNow() + 10
                
            else:
                
                cache_period = 240
                disk_cache_stop_time = HydrusData.GetNow() + 2
                
            
            if HydrusData.TimeHasPassed( self._timestamps[ 'last_disk_cache_population' ] + cache_period ):
                
                self.Read( 'load_into_disk_cache', stop_time = disk_cache_stop_time, caller_limit = disk_cache_maintenance_mb * 1024 * 1024 )
                
                self._timestamps[ 'last_disk_cache_population' ] = HydrusData.GetNow()
                
            
        
    
    def MenuIsOpen( self ):
        
        return self._menu_open
        
    
    def PageAlive( self, page_key ):
        
        with self._page_key_lock:
            
            return page_key in self._alive_page_keys
            
        
    
    def PageClosedButNotDestroyed( self, page_key ):
        
        with self._page_key_lock:
            
            return page_key in self._closed_page_keys
            
        
    
    def PopupMenu( self, window, menu ):
        
        if menu.GetMenuItemCount() > 0:
            
            self._menu_open = True
            
            window.PopupMenu( menu )
            
            self._menu_open = False
            
        
        ClientGUIMenus.DestroyMenu( window, menu )
        
    
    def PrepStringForDisplay( self, text ):
        
        return text.lower()
        
    
    def ProcessPubSub( self ):
        
        self.CallBlockingToWx( self._pubsub.Process )
        
    
    def RefreshServices( self ):
        
        self.services_manager.RefreshServices()
        
    
    def ReleasePageKey( self, page_key ):
        
        with self._page_key_lock:
            
            self._alive_page_keys.discard( page_key )
            self._closed_page_keys.discard( page_key )
            
        
    
    def ResetPageChangeTimer( self ):
        
        self._timestamps[ 'last_page_change' ] = HydrusData.GetNow()
        
    
    def RestartBooru( self ):
        
        service = self.services_manager.GetService( CC.LOCAL_BOORU_SERVICE_KEY )
        
        port = service.GetPort()
        
        def TWISTEDRestartServer():
            
            def StartServer( *args, **kwargs ):
                
                try:
                    
                    if HydrusNetworking.LocalPortInUse( port ):
                    
                        text = 'The client\'s booru server could not start because something was already bound to port ' + str( port ) + '.'
                        text += os.linesep * 2
                        text += 'This usually means another hydrus client is already running and occupying that port. It could be a previous instantiation of this client that has yet to shut itself down.'
                        text += os.linesep * 2
                        text += 'You can change the port this client tries to host its local server on in services->manage services.'
                        
                        HydrusData.ShowText( text )
                        
                        return
                        
                    
                    from . import ClientLocalServer
                    
                    self._booru_port_connection = reactor.listenTCP( port, ClientLocalServer.HydrusServiceBooru( service ) )
                    
                    if not HydrusNetworking.LocalPortInUse( port ):
                        
                        text = 'Tried to bind port ' + str( port ) + ' for the local booru, but it appeared to be already in use.'
                        
                        HydrusData.ShowText( text )
                        
                    
                except Exception as e:
                    
                    wx.CallAfter( HydrusData.ShowException, e )
                    
                
            
            if self._booru_port_connection is None:
                
                if port is not None:
                    
                    StartServer()
                    
                
            else:
                
                deferred = defer.maybeDeferred( self._booru_port_connection.stopListening )
                
                if port is not None:
                    
                    deferred.addCallback( StartServer )
                    
                
            
        
        if HG.twisted_is_broke:
            
            HydrusData.ShowText( 'Twisted failed to import, so could not restart the booru! Please contact hydrus dev!' )
            
        else:
            
            reactor.callFromThread( TWISTEDRestartServer )
            
        
    
    def RestoreDatabase( self ):
        
        restore_intro = ''
        
        with wx.DirDialog( self.gui, 'Select backup location.' ) as dlg:
            
            if dlg.ShowModal() == wx.ID_OK:
                
                path = dlg.GetPath()
                
                text = 'Are you sure you want to restore a backup from "' + path + '"?'
                text += os.linesep * 2
                text += 'Everything in your current database will be deleted!'
                text += os.linesep * 2
                text += 'The gui will shut down, and then it will take a while to complete the restore. Once it is done, the client will restart.'
                
                with ClientGUIDialogs.DialogYesNo( self.gui, text ) as dlg_yn:
                    
                    if dlg_yn.ShowModal() == wx.ID_YES:
                        
                        def THREADRestart():
                            
                            wx.CallAfter( self.gui.Exit )
                            
                            while not self.db.LoopIsFinished():
                                
                                time.sleep( 0.1 )
                                
                            
                            self.db.RestoreBackup( path )
                            
                            while not HG.shutdown_complete:
                                
                                time.sleep( 0.1 )
                                
                            
                            HydrusData.RestartProcess()
                            
                        
                        self.CallToThreadLongRunning( THREADRestart )
                        
                    
                
            
        
    
    def Run( self ):
        
        self._app = wx.App()
        
        self._app.locale = wx.Locale( wx.LANGUAGE_DEFAULT ) # Very important to init this here and keep it non garbage collected
        
        # do not import locale here and try anything clever--assume that bad locale formatting is due to OS-level mess-up, not mine
        # wx locale is supposed to set it all up nice, so if someone's doesn't, explore that and find the external solution
        
        HydrusData.Print( 'booting controller\u2026' )
        
        self.frame_icon = wx.Icon( os.path.join( HC.STATIC_DIR, 'hydrus_32_non-transparent.png' ), wx.BITMAP_TYPE_PNG )
        
        self.CreateSplash()
        
        self.CallToThreadLongRunning( self.THREADBootEverything )
        
        self._app.MainLoop()
        
        HydrusData.Print( 'shutting down controller\u2026' )
        
    
    def SaveDirtyObjects( self ):
        
        with HG.dirty_object_lock:
            
            dirty_services = [ service for service in self.services_manager.GetServices() if service.IsDirty() ]
            
            if len( dirty_services ) > 0:
                
                self.WriteSynchronous( 'dirty_services', dirty_services )
                
            
            if self.network_engine.bandwidth_manager.IsDirty():
                
                self.WriteSynchronous( 'serialisable', self.network_engine.bandwidth_manager )
                
                self.network_engine.bandwidth_manager.SetClean()
                
            
            if self.network_engine.domain_manager.IsDirty():
                
                self.WriteSynchronous( 'serialisable', self.network_engine.domain_manager )
                
                self.network_engine.domain_manager.SetClean()
                
            
            if self.network_engine.login_manager.IsDirty():
                
                self.WriteSynchronous( 'serialisable', self.network_engine.login_manager )
                
                self.network_engine.login_manager.SetClean()
                
            
            if self.network_engine.session_manager.IsDirty():
                
                self.WriteSynchronous( 'serialisable', self.network_engine.session_manager )
                
                self.network_engine.session_manager.SetClean()
                
            
        
    
    def SetServices( self, services ):
        
        with HG.dirty_object_lock:
            
            self.WriteSynchronous( 'update_services', services )
            
            self.services_manager.RefreshServices()
            
        
    
    def ShutdownModel( self ):
        
        if not HG.emergency_exit:
            
            self.file_viewing_stats_manager.Flush()
            
            self.SaveDirtyObjects()
            
        
        HydrusController.HydrusController.ShutdownModel( self )
        
    
    def ShutdownView( self ):
        
        if not HG.emergency_exit:
            
            self.pub( 'splash_set_status_text', 'waiting for daemons to exit' )
            
            self._ShutdownDaemons()
            
            if HG.do_idle_shutdown_work:
                
                try:
                    
                    self.DoIdleShutdownWork()
                    
                except:
                    
                    ClientData.ReportShutdownException()
                    
                
            
        
        HydrusController.HydrusController.ShutdownView( self )
        
    
    def SystemBusy( self ):
        
        if HG.force_idle_mode:
            
            return False
            
        
        max_cpu = self.options[ 'idle_cpu_max' ]
        
        if max_cpu is None:
            
            self._system_busy = False
            
        else:
            
            if HydrusData.TimeHasPassed( self._timestamps[ 'last_cpu_check' ] + 60 ):
                
                cpu_times = psutil.cpu_percent( percpu = True )
                
                if True in ( cpu_time > max_cpu for cpu_time in cpu_times ):
                    
                    self._system_busy = True
                    
                else:
                    
                    self._system_busy = False
                    
                
                self._timestamps[ 'last_cpu_check' ] = HydrusData.GetNow()
                
            
        
        return self._system_busy
        
    
    def THREADBootEverything( self ):
        
        try:
            
            self.CheckAlreadyRunning()
            
            self._last_shutdown_was_bad = HydrusData.LastShutdownWasBad( self.db_dir, 'client' )
            
            HydrusData.RecordRunningStart( self.db_dir, 'client' )
            
            self.InitModel()
            
            self.InitView()
            
            self._is_booted = True
            
        except HydrusExceptions.PermissionException as e:
            
            HydrusData.Print( e )
            
            HG.emergency_exit = True
            
            self.Exit()
            
        except Exception as e:
            
            text = 'A serious error occurred while trying to start the program. The error will be shown next in a window. More information may have been written to client.log.'
            
            HydrusData.DebugPrint( 'If the db crashed, another error may be written just above ^.' )
            HydrusData.DebugPrint( text )
            
            HydrusData.DebugPrint( traceback.format_exc() )
            
            wx.CallAfter( wx.MessageBox, traceback.format_exc() )
            wx.CallAfter( wx.MessageBox, text )
            
            HG.emergency_exit = True
            
            self.Exit()
            
        finally:
            
            self._DestroySplash()
            
        
    
    def THREADExitEverything( self ):
        
        try:
            
            self.pub( 'splash_set_title_text', 'shutting down gui\u2026' )
            
            self.ShutdownView()
            
            self.pub( 'splash_set_title_text', 'shutting down db\u2026' )
            
            self.ShutdownModel()
            
            self.pub( 'splash_set_title_text', 'cleaning up\u2026' )
            self.pub( 'splash_set_status_text', '' )
            
            HydrusData.CleanRunningFile( self.db_dir, 'client' )
            
        except HydrusExceptions.PermissionException:
            
            pass
            
        except HydrusExceptions.ShutdownException:
            
            pass
            
        except:
            
            ClientData.ReportShutdownException()
            
        finally:
            
            self._DestroySplash()
            
        
    
    def ToClipboard( self, data_type, data ):
        
        # need this cause can't do it in a non-gui thread
        
        if data_type == 'paths':
            
            paths = data
            
            if wx.TheClipboard.Open():
                
                data = wx.DataObjectComposite()
                
                file_data = wx.FileDataObject()
                
                for path in paths: file_data.AddFile( path )
                
                text_data = wx.TextDataObject( os.linesep.join( paths ) )
                
                data.Add( file_data, True )
                data.Add( text_data, False )
                
                wx.TheClipboard.SetData( data )
                
                wx.TheClipboard.Close()
                
            else: wx.MessageBox( 'Could not get permission to access the clipboard!' )
            
        elif data_type == 'text':
            
            text = data
            
            if wx.TheClipboard.Open():
                
                data = wx.TextDataObject( text )
                
                wx.TheClipboard.SetData( data )
                
                wx.TheClipboard.Close()
                
            else: wx.MessageBox( 'I could not get permission to access the clipboard.' )
            
        elif data_type == 'bmp':
            
            media = data
            
            image_renderer = self.GetCache( 'images' ).GetImageRenderer( media )
            
            def CopyToClipboard():
                
                if wx.TheClipboard.Open():
                    
                    wx_bmp = image_renderer.GetWXBitmap()
                    
                    data = wx.BitmapDataObject( wx_bmp )
                    
                    wx.TheClipboard.SetData( data )
                    
                    wx.TheClipboard.Close()
                    
                else:
                    
                    wx.MessageBox( 'I could not get permission to access the clipboard.' )
                    
                
            
            def THREADWait():
                
                # have to do this in thread, because the image needs the wx event queue to render
                
                start_time = time.time()
                
                while not image_renderer.IsReady():
                    
                    if HydrusData.TimeHasPassed( start_time + 15 ):
                        
                        raise Exception( 'The image did not render in fifteen seconds, so the attempt to copy it to the clipboard was abandoned.' )
                        
                    
                    time.sleep( 0.1 )
                    
                
                wx.CallAfter( CopyToClipboard )
                
            
            self.CallToThread( THREADWait )
            
        
    
    def UnclosePageKeys( self, page_keys ):
        
        with self._page_key_lock:
            
            self._closed_page_keys.difference_update( page_keys )
            
        
    
    def WaitUntilViewFree( self ):
        
        self.WaitUntilModelFree()
        
        self.WaitUntilThumbnailsFree()
        
    
    def WaitUntilThumbnailsFree( self ):
        
        while True:
            
            if self._view_shutdown:
                
                raise HydrusExceptions.ShutdownException( 'Application shutting down!' )
                
            elif not self._caches[ 'thumbnail' ].DoingWork():
                
                return
                
            else:
                
                time.sleep( 0.00001 )
                
            
        
    
    def Write( self, action, *args, **kwargs ):
        
        if action == 'content_updates':
            
            self._managers[ 'undo' ].AddCommand( 'content_updates', *args, **kwargs )
            
        
        return HydrusController.HydrusController.Write( self, action, *args, **kwargs )
        
    
