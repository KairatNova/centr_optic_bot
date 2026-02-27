from aiogram.fsm.state import State, StatesGroup


# Для регистрации пользователя по номеру
class RegistrationStates(StatesGroup):
    waiting_for_phone = State()



# Для владельца — редактирование контента

class OwnerContentStates(StatesGroup):
    choosing_section = State()      # Выбор раздела для редактирования
    waiting_new_text = State()      # Ожидание нового текста


class OwnerMainStates(StatesGroup):
    main_menu = State()

class OwnerAdminsStates(StatesGroup):
    admins_menu = State()           # подменю управления админами
    waiting_for_add_input = State() # ожидание telegram_id или телефона для добавления
    waiting_for_delete_input = State()  # ожидание для удаления



class OwnerBroadcastStates(StatesGroup):
    broadcast_menu = State()                # подменю рассылок
    waiting_search_query = State()          # ожидание строки поиска
    viewing_profile = State()               # просмотр профиля (data: person_id)
    waiting_message_text = State()          # ожидание текста сообщения (data: person_id)
    waiting_broadcast_text = State()  # ожидание текста рассылки (data: list of person_ids)

class OwnerClientsStates(StatesGroup):
    clients_menu = State()           # главное меню клиентов
    waiting_search_query = State()     # поиск клиента
    viewing_client_profile = State()   # просмотр профиля
    editing_client_data = State()      # редактирование имени/возраста
    waiting_sph_cyl_axis = State()
    waiting_pd_lens_frame = State()
    waiting_note = State()
    viewing_vision = State()  # просмотр одной записи с пагинацией
    waiting_confirm_delete = State()  # подтверждение удаления
    waiting_sph_cyl_axis_edit = State()  # редактирование шага 1
    waiting_pd_lens_frame_edit = State()  # редактирование шага 2
    waiting_note_edit = State()  # редактирование шага 3




    waiting_delete_confirm = State()    # подтверждение удаления'''


# Новые состояния (добавьте в forms_fsm.py)
class OwnerExportStates(StatesGroup):
    export_menu = State()  # подменю выгрузок


# Состояния администратора (Admin)
class AdminMainStates(StatesGroup):
    admin_menu = State()               # главное меню админа

class AdminBroadcastStates(StatesGroup):
    waiting_search_query = State()
    viewing_profile = State()
    waiting_message_text = State()

class AdminClientsStates(StatesGroup):
    waiting_search_query = State()
    viewing_profile = State()                     # ← здесь должно быть AdminClientsStates
    editing_client_data = State()

    waiting_sph_cyl_axis = State()               # добавление
    waiting_pd_lens_frame = State()
    waiting_note = State()

    waiting_sph_cyl_axis_edit = State()
    waiting_pd_lens_frame_edit = State()
    waiting_note_edit = State()




