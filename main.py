import flet as ft
import time  # Added for the timer
import threading  # Added for the timer
from flet import (
    Page, Text, Row, Column, Container, ElevatedButton, IconButton, Icon,
    Tabs, Tab, TextField, Dropdown, SnackBar, BoxShadow, BorderSide,
    ThemeMode, LinearGradient, CircleBorder, RoundedRectangleBorder,
    FontWeight, TextAlign, ScrollMode, GridView, BorderRadius,
    Colors, Icons, Theme  
)

def main(page: Page):
    page.title = "Agent Workspace"
    page.theme_mode = ThemeMode.LIGHT
    page.padding = 0
    page.fonts = {
        "Orbitron": "https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&display=swap",
        "Inter": "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    }
    page.theme = Theme(font_family="Inter")

    # --- State ---
    current_status = "Available"
    call_state = "idle"
    phone_number = ""
    timer_seconds = 0
    timer_running = False

    # --- Helpers ---
    def format_time(seconds):
        return f"{seconds // 60:02}:{seconds % 60:02}"

    def show_toast(message: str, error: bool = False):
        page.show_snack_bar(
            SnackBar(
                content=Text(message, color=Colors.RED if error else Colors.GREEN),
                bgcolor=Colors.RED_50 if error else Colors.GREEN_50,
                action="Dismiss",
                duration=3000
            )
        )

    def start_call():
        nonlocal timer_seconds, timer_running
        timer_seconds = 0
        timer_running = True
        phone_display.value = "CONNECTED"
        phone_display.color = Colors.GREEN_ACCENT_400  
        phone_timer.visible = True
        phone_hangup_btn.visible = True
        phone_call_btn.visible = False
        update_call_status("connected")
        page.update()

    def end_call():
        nonlocal timer_running
        timer_running = False
        phone_display.value = "READY"
        phone_display.color = Colors.WHITE  
        phone_timer.visible = False
        phone_hangup_btn.visible = False
        phone_call_btn.visible = True
        update_call_status("idle")
        page.update()

    def update_call_status(state: str):
        nonlocal call_state
        call_state = state
        badge = call_status_badge
        # Update text color inside the Text control
        badge.content.value = state.capitalize()
        
        if state == "connected":
            badge.bgcolor = Colors.GREEN_100  
            badge.content.color = Colors.GREEN  
            badge.border = ft.BorderSide(1, Colors.GREEN)  
        elif state == "ringing":
            badge.bgcolor = Colors.ORANGE_100  
            badge.content.color = Colors.ORANGE  
            badge.border = ft.BorderSide(1, Colors.ORANGE)  
        else:  # idle
            badge.bgcolor = Colors.GREY_100  
            badge.content.color = Colors.GREY  
            badge.border = ft.BorderSide(1, Colors.GREY_300)  
        badge.update()

    def set_status(new_status: str, reason: str = ""):
        nonlocal current_status
        current_status = new_status
        status_pill.content.value = new_status
        status_pill.bgcolor = Colors.RED if new_status.lower() != "available" else Colors.BLUE  
        page.update()
        show_toast(f"Status changed to: {new_status}")

    def toggle_theme(e):
        page.theme_mode = ThemeMode.DARK if page.theme_mode == ThemeMode.LIGHT else ThemeMode.LIGHT
        theme_icon.icon = Icons.DARK_MODE if page.theme_mode == ThemeMode.LIGHT else Icons.LIGHT_MODE
        page.update()

    # --- UI Components ---

    theme_icon = IconButton(
        icon=Icons.LIGHT_MODE,
        on_click=toggle_theme,
        tooltip="Toggle theme",
        icon_color=Colors.RED  
    )
    
    status_pill = Container(
        content=Text(
            current_status, 
            weight=FontWeight.BOLD, 
            size=12, 
            color=Colors.WHITE 
        ),
        padding=ft.padding.symmetric(horizontal=12, vertical=10),
        bgcolor=Colors.RED,  
        border_radius=6,
        shadow=BoxShadow(blur_radius=8, color=Colors.with_opacity(0.3, Colors.RED))  
    )
    
    header = Container(
        content=Row(
            controls=[
                Column([
                    Text("Welcome back, Alex 👋", size=20, weight=FontWeight.BOLD),
                    Text("Stay available to receive the next 3 campaigns.", size=13, color=Colors.GREY_600)  
                ], spacing=2),
                Row([theme_icon, status_pill], spacing=16, alignment=ft.MainAxisAlignment.END)
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        ),
        padding=ft.padding.symmetric(horizontal=32, vertical=20),
        bgcolor=Colors.WHITE,  
        border=ft.Border(bottom=ft.BorderSide(2, Colors.RED)),  
        shadow=BoxShadow(blur_radius=10, color=Colors.with_opacity(0.2, Colors.BLACK))  
    )

    def make_status_chip(icon: str, label: str, status: str):
        return ElevatedButton(
            content=Row([Icon(icon), Text(label)], tight=True),
            style=ft.ButtonStyle(
                bgcolor=Colors.RED if status == "offline" else Colors.GREY_200,  
                color=Colors.WHITE if status == "offline" else Colors.BLACK,  
                shape=RoundedRectangleBorder(radius=6)
            ),
            on_click=lambda _: set_status(status)
        )

    status_actions = Row(
        controls=[
            make_status_chip(Icons.HEADSET, "Available", "available"),
            make_status_chip(Icons.COFFEE, "Break", "break"), 
            make_status_chip(Icons.LUNCH_DINING, "Lunch", "lunch"),
            make_status_chip(Icons.SCHOOL, "Training", "training"),
            make_status_chip(Icons.PEOPLE, "Meeting", "meeting"),
            make_status_chip(Icons.POWER_OFF, "Offline", "offline")
        ],
        wrap=True,
        spacing=12,
        run_spacing=12
    )

    def info_card(title: str, value: str, subtitle: str = ""):
        return Container(
            content=Column([
                Text(title, size=10, color=Colors.GREY, weight=FontWeight.BOLD),  
                Text(value, size=16, weight=FontWeight.BOLD),
                Text(subtitle, size=12, color=Colors.GREY_700) if subtitle else Container()  
            ], spacing=4),
            padding=20,
            bgcolor=Colors.GREY_50,  
            border_radius=6,
            border=ft.border.all(1, Colors.GREY_300)  
        )

    cards_row = Row(
        controls=[
            info_card("Extension", "101", "Softphone registered"),
            info_card("Assigned Campaigns", "3 active", ""),
            info_card("Callbacks (next 24h)", "2", "")
        ],
        wrap=True,
        spacing=16
    )

    transfer_select = Dropdown(
        options=[
            ft.dropdown.Option("102", "Sarah (102)"),
            ft.dropdown.Option("103", "Mark (103)"),
        ],
        label="Available Agents",
        width=300
    )
    transfer_btn = ElevatedButton("Transfer Call", disabled=True, bgcolor=Colors.RED, color=Colors.WHITE)  

    call_status_badge = Container(
        content=Text(
            "Idle", 
            size=14, 
            weight=FontWeight.BOLD, 
            color=Colors.GREY 
        ),
        padding=10,
        border_radius=6,
        bgcolor=Colors.GREY_100,  
        border=ft.border.all(1, Colors.GREY_300),  
        alignment=ft.alignment.center
    )

    phone_display = Text("READY", size=24, font_family="Orbitron", color=Colors.WHITE, text_align=TextAlign.CENTER)  
    phone_timer = Text("00:00", size=20, font_family="Orbitron", color=Colors.CYAN_ACCENT, visible=False, text_align=TextAlign.CENTER)  
    phone_number_display = Text("—", size=20, font_family="Orbitron", color=Colors.LIME_ACCENT, text_align=TextAlign.RIGHT)  

    call_details = Column(
        controls=[
            Row([Text("Number:"), Text("—", weight=FontWeight.BOLD)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            Row([Text("Status:"), call_status_badge]),
            Row([Text("Duration:"), Text("00:00", weight=FontWeight.BOLD)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ],
        spacing=8
    )

    live_call_content = Column(
        controls=[
            Container(
                content=Column([
                    Text("Current Call", size=16, weight=FontWeight.BOLD),
                    Text("The dialer connects you automatically when a lead answers.", size=12, color=Colors.GREY_600)  
                ], spacing=4),
                padding=ft.padding.only(bottom=16)
            ),
            Container(
                content=Text("No call connected. Stay available to auto-connect.", color=Colors.GREY),  
                padding=32,
                border=ft.border.all(2, Colors.GREY_300),  
                border_radius=6,
                alignment=ft.alignment.center
            ),
            Container(content=call_details, visible=False)
        ],
        spacing=12
    )

    scripts_content = Container(
        content=Column([
            Text("Call Script", size=16, weight=FontWeight.BOLD),
            Text("Hello! Thank you for calling Acme Corp...", selectable=True)
        ], spacing=10),
        padding=16,
        bgcolor=Colors.GREY_50,  
        border_radius=6
    )

    notes_field = TextField(
        label="Quick Notes",
        multiline=True,
        min_lines=8,
        max_lines=12,
        hint_text="e.g. Customer asked for pricing details..."
    )
    notes_content = Column([notes_field], spacing=12)

    tabs = Tabs(
        selected_index=0,
        tabs=[
            Tab(text="Live Call Feed", icon=Icons.PHONE, content=live_call_content),
            Tab(text="Scripts", icon=Icons.DESCRIPTION, content=scripts_content),
            Tab(text="Quick Notes", icon=Icons.NOTE, content=notes_content),
        ],
        expand=True
    )

    def on_key(e):
        nonlocal phone_number
        key = e.control.data
        if key == "clear":
            phone_number = ""
        elif key == "call":
            if phone_number:
                start_call()
            return
        elif key == "hangup":
            end_call()
            return
        elif len(phone_number) < 15 and (key.isdigit() or key in "*#"):
            phone_number += key
        phone_number_display.value = phone_number or "—"
        phone_number_display.update()

    keypad = GridView(
        runs_count=3,
        max_extent=80,
        spacing=8,
        run_spacing=8,
        controls=[
            ElevatedButton(data=str(i), text=str(i), on_click=on_key, style=ft.ButtonStyle(shape=CircleBorder())) for i in range(1, 10)
        ] + [
            ElevatedButton(data="*", text="*", on_click=on_key, style=ft.ButtonStyle(shape=CircleBorder())),
            ElevatedButton(data="0", text="0", on_click=on_key, style=ft.ButtonStyle(shape=CircleBorder())),
            ElevatedButton(data="#", text="#", on_click=on_key, style=ft.ButtonStyle(shape=CircleBorder())),
        ]
    )

    phone_call_btn = ElevatedButton("CALL", icon=Icons.PHONE, on_click=on_key, data="call", bgcolor=Colors.GREEN, color=Colors.WHITE, expand=True)  
    
    # --- FIXED: Icons.PHONE_OFF -> Icons.CALL_END ---
    phone_hangup_btn = ElevatedButton("HANG UP", icon=Icons.CALL_END, on_click=on_key, data="hangup", bgcolor=Colors.RED, color=Colors.WHITE, expand=True, visible=False)  

    retro_phone = Container(
        content=Column([
            Text("EASYIAN PHONE", size=14, font_family="Orbitron", color=Colors.GREY_400, text_align=TextAlign.CENTER),  
            ft.Divider(height=10, color=Colors.TRANSPARENT),  
            Container(
                content=Column([
                    phone_number_display,
                    phone_display,
                    phone_timer,
                    Text("Extension: 101", size=12, color=Colors.GREY_400, text_align=TextAlign.CENTER),  
                ], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                padding=20,
                bgcolor=Colors.BLACK,  
                border_radius=8,
            ),
            keypad,
            Column([phone_call_btn, phone_hangup_btn], spacing=8)
        ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=24,
        bgcolor=Colors.GREY_900,  
        border_radius=20,
        gradient=LinearGradient(begin=ft.alignment.top_left, end=ft.alignment.bottom_right, colors=[Colors.GREY_900, Colors.BLUE_GREY_800]),  
        shadow=BoxShadow(blur_radius=20, color=Colors.with_opacity(0.5, Colors.BLACK))  
    )

    main_layout = Row(
        controls=[
            Column([
                Text("Availability", size=18, weight=FontWeight.BOLD, color=Colors.RED),  
                Text("Update your state so the dialer knows when to connect calls.", size=13, color=Colors.GREY_600),  
                status_actions,
                cards_row,
                ft.Divider(height=24),
                Text("Call Transfer", size=18, weight=FontWeight.BOLD, color=Colors.RED),  
                transfer_select,
                # --- FIXED: Corrected the typo 'GREY_6G00' -> 'GREY_600' ---
                Text("Transfer button enables when you are on a live call.", size=12, color=Colors.GREY_600),  
                transfer_btn
            ], spacing=16, expand=True),
            Column([tabs], expand=True),
            Column([retro_phone], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        ],
        expand=True,
        spacing=24,
        scroll=ScrollMode.ADAPTIVE
    )
    
    # --- Timer Thread (FIXED) ---
    def timer_thread():
        """
        Runs in a separate thread to update the call timer every second.
        """
        while True:
            if timer_running:
                # Use nonlocal to modify the variable from the outer scope
                nonlocal timer_seconds
                timer_seconds += 1
                phone_timer.value = format_time(timer_seconds)
                # Update only the timer control from the thread
                try:
                    # Check if page is still available before updating
                    if page:
                        phone_timer.update()
                except Exception as e:
                    # Handle exceptions if page context is lost (e.g., app closed)
                    print(f"Error updating timer: {e}")
                    break
            # Wait for 1 second before the next check
            time.sleep(1)

    page.add(
        Column([
            header,
            Container(main_layout, padding=ft.padding.all(24), expand=True)
        ], expand=True)
    )

    # Start the timer thread
    # daemon=True ensures the thread exits when the main program exits
    t = threading.Thread(target=timer_thread, daemon=True)
    t.start()


if __name__ == "__main__":
    ft.app(
        target=main,
        view=ft.WEB_BROWSER,
        port=8000
    )