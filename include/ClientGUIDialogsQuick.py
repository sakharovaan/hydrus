from . import ClientGUIScrolledPanelsEdit
from . import ClientGUITopLevelWindows
from . import HydrusExceptions
import wx

def GetDeleteFilesJobs( win, media, default_reason, suggested_file_service_key = None ):
    
    title = 'Delete files?'
    
    with ClientGUITopLevelWindows.DialogEdit( win, title, frame_key = 'regular_center_dialog' ) as dlg:
        
        panel = ClientGUIScrolledPanelsEdit.EditDeleteFilesPanel( dlg, media, default_reason, suggested_file_service_key = suggested_file_service_key )
        
        dlg.SetPanel( panel )
        
        if panel.QuestionIsAlreadyResolved():
            
            ( involves_physical_delete, jobs ) = panel.GetValue()
            
            return ( involves_physical_delete, jobs )
            
        
        if dlg.ShowModal() == wx.ID_OK:
            
            ( involves_physical_delete, jobs ) = panel.GetValue()
            
            return ( involves_physical_delete, jobs )
            
        else:
            
            raise HydrusExceptions.CancelledException()
            
        
    
def SelectFromList( win, title, choice_tuples, value_to_select = None, sort_tuples = True ):
    
    with ClientGUITopLevelWindows.DialogEdit( win, title ) as dlg:
        
        panel = ClientGUIScrolledPanelsEdit.EditSelectFromListPanel( dlg, choice_tuples, value_to_select = value_to_select, sort_tuples = sort_tuples )
        
        dlg.SetPanel( panel )
        
        if dlg.ShowModal() == wx.ID_OK:
            
            result = panel.GetValue()
            
            return result
            
        else:
            
            raise HydrusExceptions.CancelledException()
            
        
    
def SelectFromListButtons( win, title, choice_tuples ):
    
    with ClientGUITopLevelWindows.DialogEdit( win, title, hide_buttons = True ) as dlg:
        
        panel = ClientGUIScrolledPanelsEdit.EditSelectFromListButtonsPanel( dlg, choice_tuples )
        
        dlg.SetPanel( panel )
        
        if dlg.ShowModal() == wx.ID_OK:
            
            result = panel.GetValue()
            
            return result
            
        else:
            
            raise HydrusExceptions.CancelledException()
            
        
    
