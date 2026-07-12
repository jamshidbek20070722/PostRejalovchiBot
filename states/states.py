from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    # Admin administration
    adding_admin = State()
    removing_admin = State()
    
    # Channel administration
    adding_channel = State()
    removing_channel = State()
    updating_footer_channel_select = State()
    updating_footer_text = State()
    force_sub_toggle = State()

class PostCreationStates(StatesGroup):
    # Ingestion flow
    waiting_for_channel = State()
    waiting_for_forwarded_posts = State()
    
    # Scheduling configuration
    waiting_for_schedule_mode = State()
    waiting_for_schedule_time = State()
    waiting_for_reminders = State()
    waiting_for_reactions = State()
