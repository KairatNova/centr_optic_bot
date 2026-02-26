from aiogram.fsm.state import State, StatesGroup


# Для регистрации пользователя по номеру
class RegistrationStates(StatesGroup):
    waiting_for_phone = State()





class OwnerContentStates(StatesGroup):
    choosing_section = State()      # Выбор раздела для редактирования
    waiting_new_text = State()      # Ожидание нового текста


class OwnerMainStates(StatesGroup):
    main_menu = State()

class OwnerAdminsStates(StatesGroup):
    admins_menu = State()           
    waiting_for_add_input = State() 
    waiting_for_delete_input = State()  



class OwnerBroadcastStates(StatesGroup):
    broadcast_menu = State()          
    waiting_search_query = State()    
    viewing_profile = State()         
    waiting_message_text = State()    
    waiting_broadcast_text = State()  

class OwnerClientsStates(StatesGroup):
    clients_menu = State()           
    waiting_search_query = State()   
    viewing_client_profile = State() 
    editing_client_data = State()    
    waiting_sph_cyl_axis = State()
    waiting_pd_lens_frame = State()
    waiting_note = State()
    viewing_vision = State()  # просмотр одной записи с пагинацией
    waiting_confirm_delete = State()  
    waiting_sph_cyl_axis_edit = State()  
    waiting_pd_lens_frame_edit = State()  
    waiting_note_edit = State()  







class OwnerExportStates(StatesGroup):
    export_menu = State() 

# Состояния администратора (Admin)
class AdminMainStates(StatesGroup):
    admin_menu = State()               

class AdminBroadcastStates(StatesGroup):
    waiting_search_query = State()
    viewing_profile = State()
    waiting_message_text = State()

class AdminClientsStates(StatesGroup):
    waiting_search_query = State()
    viewing_profile = State()                     
    editing_client_data = State()

    waiting_sph_cyl_axis = State()              
    waiting_pd_lens_frame = State()
    waiting_note = State()

    waiting_sph_cyl_axis_edit = State()
    waiting_pd_lens_frame_edit = State()
    waiting_note_edit = State()




