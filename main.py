import flet as ft

def main(page: ft.Page):
    page.title = "FINANCE [1.12.23.208] FOR DEMO COMPANY - [Gold Loan CRM]"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window_width = 1200
    page.window_height = 800
    page.window_maximized = True
    page.theme_mode = ft.ThemeMode.LIGHT # Start with light mode for glossy effect
    page.padding = 0 # Remove default page padding

    # Custom colors for a modern, glossy Gold Loan CRM look
    primary_gold = "#FFD700" # Gold color
    dark_blue = "#1A237E" # Dark Indigo for accents
    light_grey_bg = "#F5F5F5" # Very light grey background
    card_background = "#FFFFFF" # White for cards
    text_color_dark = "#212121" # Dark grey for text
    text_color_light = "#FFFFFF" # White for text on dark backgrounds
    glossy_gradient_light = ft.LinearGradient(
        begin=ft.alignment.top_left,
        end=ft.alignment.bottom_right,
        colors=["#E0E0E0", "#FFFFFF", "#E0E0E0"],
        stops=[0.0, 0.5, 1.0]
    )
    glossy_gradient_gold = ft.LinearGradient(
        begin=ft.alignment.top_left,
        end=ft.alignment.bottom_right,
        colors=["#FFECB3", "#FFD700", "#FFECB3"],
        stops=[0.0, 0.5, 1.0]
    )

    # --- Navigation Logic ---
    def route_change(route):
        page.views.clear()
        page.views.append(
            # Base view for the application, always present
            ft.View(
                "/",
                [
                    top_nav,
                    dashboard_content, # Dashboard is the default view, now directly added
                    bottom_status
                ],
                padding=0,
                spacing=0
            )
        )
        if page.route == "/master":
            page.views.append(
                ft.View(
                    "/master",
                    [
                        top_nav,
                        MasterView(), # Removed ft.Expanded, MasterView is already expanding
                        bottom_status
                    ],
                    padding=0,
                    spacing=0
                )
            )
        elif page.route == "/transaction":
            page.views.append(
                ft.View(
                    "/transaction",
                    [
                        top_nav,
                        TransactionView(), # Removed ft.Expanded
                        bottom_status
                    ],
                    padding=0,
                    spacing=0
                )
            )
        elif page.route == "/account":
            page.views.append(
                ft.View(
                    "/account",
                    [
                        top_nav,
                        AccountView(), # Removed ft.Expanded
                        bottom_status
                    ],
                    padding=0,
                    spacing=0
                )
            )
        elif page.route == "/report":
            page.views.append(
                ft.View(
                    "/report",
                    [
                        top_nav,
                        ReportView(), # Removed ft.Expanded
                        bottom_status
                    ],
                    padding=0,
                    spacing=0
                )
            )
        elif page.route == "/crm":
            page.views.append(
                ft.View(
                    "/crm",
                    [
                        top_nav,
                        CrmGoldLoanView(), # Removed ft.Expanded
                        bottom_status
                    ],
                    padding=0,
                    spacing=0
                )
            )
        page.update()

    def view_pop(view):
        page.views.pop()
        top_view = page.views[-1]
        page.go(top_view.route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    # --- UI Components ---

    def create_menu_item(text, route=None):
        def on_click(e):
            if route:
                page.go(route)
            else:
                # Handle cases where no specific route is defined, e.g., show a message
                print(f"{text} clicked (no specific route)")
        return ft.TextButton(
            content=ft.Text(text, size=14, weight=ft.FontWeight.BOLD, color=text_color_dark),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=5),
                padding=ft.padding.symmetric(horizontal=15, vertical=10),
                overlay_color={"hovered": ft.Colors.BLUE_GREY_100},
            ),
            on_click=on_click
        )

    def create_dashboard_card(icon_name, title, value, color, is_due_reminder=False):
        content = [
            ft.Icon(name=icon_name, color=color, size=36),
            ft.Text(title, size=14, weight=ft.FontWeight.W_500, color=text_color_dark),
            ft.Text(value, size=20, weight=ft.FontWeight.BOLD, color=text_color_dark),
        ]
        if is_due_reminder:
            content.append(ft.Text("[4]", size=12, color=ft.Colors.RED_500, weight=ft.FontWeight.BOLD))

        return ft.Container(
            content=ft.Column(
                content,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=5
            ),
            width=180,
            height=120,
            padding=ft.padding.all(10),
            alignment=ft.alignment.center,
            border_radius=ft.border_radius.all(15),
            bgcolor=card_background,
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=5,
                color=ft.Colors.BLACK12, # Corrected: BLACK_12 to BLACK12
                offset=ft.Offset(0, 2),
            ),
            gradient=glossy_gradient_light if not is_due_reminder else None,
            border=ft.border.all(1, color),
        )

    def create_feature_box(icon_name, text, color):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(name=icon_name, color=color, size=30),
                    ft.Text(text, size=12, weight=ft.FontWeight.W_500, color=text_color_dark, text_align=ft.TextAlign.CENTER),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=5
            ),
            width=120,
            height=100,
            padding=ft.padding.all(10),
            alignment=ft.alignment.center,
            border_radius=ft.border_radius.all(10),
            bgcolor=card_background,
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=3,
                color=ft.Colors.BLACK12, # Corrected: BLACK_12 to BLACK12
                offset=ft.Offset(0, 1),
            ),
            gradient=glossy_gradient_light,
            border=ft.border.all(1, color),
        )

    # --- Top Navigation Bar ---
    top_nav = ft.Container(
        content=ft.Row(
            [
                ft.Row([
                    create_menu_item("Master", "/master"),
                    create_menu_item("Transaction", "/transaction"),
                    create_menu_item("Account", "/account"),
                    create_menu_item("Report", "/report"),
                    create_menu_item("Currency Management"),
                    create_menu_item("Windows"),
                    create_menu_item("Change Theme"),
                    create_menu_item("Cibil Report"),
                    create_menu_item("Contact Us"),
                ], spacing=0),
                ft.Row([
                    ft.IconButton(ft.Icons.MINIMIZE, tooltip="Minimize"),
                    ft.IconButton(ft.Icons.FULLSCREEN, tooltip="Maximize"),
                    ft.IconButton(ft.Icons.CLOSE, tooltip="Close"),
                ])
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.padding.symmetric(horizontal=10, vertical=5),
        bgcolor=dark_blue,
        width=page.window_width,
        height=40,
        border_radius=ft.border_radius.vertical(top=0, bottom=5)
    )

    # --- Dashboard Content (Default View) ---
    dashboard_content = ft.Container(
        content=ft.Row(
            [
                # Left Section (Main Dashboard Cards)
                ft.Column(
                    [
                        ft.Row(
                            [
                                create_feature_box(ft.Icons.CALENDAR_TODAY, "Daily Loan", ft.Colors.GREEN_500),
                                create_feature_box(ft.Icons.REPLAY, "Recurring Loan", ft.Colors.BLUE_500),
                                create_feature_box(ft.Icons.MONEY, "Monthly Interest Loan", ft.Colors.ORANGE_500),
                                create_feature_box(ft.Icons.CREDIT_CARD, "Cash Credit Due", ft.Colors.PURPLE_500),
                                create_feature_box(ft.Icons.HOME_WORK, "Fix EMI Loan", ft.Colors.RED_500),
                                create_feature_box(ft.Icons.ACCOUNT_BALANCE, "ATM Loan", ft.Colors.TEAL_500),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            spacing=20,
                            wrap=True
                        ),
                        ft.Divider(height=20, color="transparent"),
                        ft.Row(
                            [
                                create_dashboard_card(ft.Icons.MONEY, "Cash Credit Due", "0.00", ft.Colors.GREEN_700),
                                create_dashboard_card(ft.Icons.PAYMENT, "EMI Monthly Due Payment", "7,00,123.00", ft.Colors.BLUE_700),
                                create_dashboard_card(ft.Icons.RECEIPT, "Receivable Payment(Daily)", "25,58,143.00", ft.Colors.ORANGE_700),
                                create_dashboard_card(ft.Icons.COLLECTIONS_BOOKMARK, "Daily Collection Report", "0.00", ft.Colors.PURPLE_700),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            spacing=20,
                            wrap=True
                        ),
                        ft.Divider(height=20, color="transparent"),
                        ft.Row(
                            [
                                create_dashboard_card(ft.Icons.CALENDAR_MONTH, "Monthly Due Interest", "3,06,975.24", ft.Colors.RED_700),
                                create_dashboard_card(ft.Icons.INTERESTS, "Due ATM Loan Interest", "3,958.00", ft.Colors.TEAL_700),
                                create_dashboard_card(ft.Icons.TODAY, "Today Reminder", "[0]", ft.Colors.BROWN_700),
                                create_dashboard_card(ft.Icons.WARNING, "Due Reminder", "[4]", ft.Colors.DEEP_ORANGE_700, is_due_reminder=True),
                                create_dashboard_card(ft.Icons.UPDATE, "UpComing Reminder", "[0]", ft.Colors.INDIGO_700),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            spacing=20,
                            wrap=True
                        ),
                        ft.Divider(height=20, color="transparent"),
                        ft.Row(
                            [
                                create_feature_box(ft.Icons.REPLAY_CIRCLE_FILLED, "Recurring Report", ft.Colors.GREEN_500),
                                create_feature_box(ft.Icons.RECEIPT_LONG, "Due Payment Report (ATM)", ft.Colors.BLUE_500),
                                create_feature_box(ft.Icons.CALENDAR_VIEW_DAY, "Due Payment Report (Daily)", ft.Colors.ORANGE_500),
                                create_feature_box(ft.Icons.CALENDAR_MONTH, "Due Payment Report (Monthly Interest)", ft.Colors.PURPLE_500),
                                create_feature_box(ft.Icons.CREDIT_SCORE, "Due Payment Report (Cash Credit)", ft.Colors.RED_500),
                                create_feature_box(ft.Icons.HOME_WORK, "Due Payment Report (Fix EMI)", ft.Colors.TEAL_500),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            spacing=20,
                            wrap=True
                        ),
                        ft.Divider(height=20, color="transparent"),
                        ft.Row(
                            [
                                ft.TextButton(
                                    content=ft.Text("Monthly Loan Due Date [0]", color=ft.Colors.BLUE_700, size=14, weight=ft.FontWeight.BOLD),
                                    style=ft.ButtonStyle(
                                        shape=ft.RoundedRectangleBorder(radius=5),
                                        padding=ft.padding.symmetric(horizontal=15, vertical=10),
                                        overlay_color={"hovered": ft.Colors.BLUE_GREY_100},
                                    )
                                ),
                                ft.TextButton(
                                    content=ft.Text("Maturity Due Date [354]", color=ft.Colors.BLUE_700, size=14, weight=ft.FontWeight.BOLD),
                                    style=ft.ButtonStyle(
                                        shape=ft.RoundedRectangleBorder(radius=5),
                                        padding=ft.padding.symmetric(horizontal=15, vertical=10),
                                        overlay_color={"hovered": ft.Colors.BLUE_GREY_100},
                                    )
                                ),
                                ft.ElevatedButton(
                                    "Send Pending Reminder",
                                    icon=ft.Icons.SEND,
                                    bgcolor=dark_blue,
                                    color=ft.Colors.WHITE,
                                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                                ),
                                ft.ElevatedButton(
                                    "Export To Excel",
                                    icon=ft.Icons.UPLOAD_FILE,
                                    bgcolor=dark_blue,
                                    color=ft.Colors.WHITE,
                                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                                ),
                                ft.ElevatedButton(
                                    "Refresh DashBoard",
                                    icon=ft.Icons.REFRESH,
                                    bgcolor=dark_blue,
                                    color=ft.Colors.WHITE,
                                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            spacing=15,
                            wrap=True
                        ),
                        ft.Divider(height=20, color="transparent"),
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Image(
                                        src="https://placehold.co/150x100/A0A0A0/FFFFFF?text=ICESTONE+SOFTWARE",
                                        width=150,
                                        height=100,
                                        fit=ft.ImageFit.CONTAIN
                                    ),
                                    ft.Column(
                                        [
                                            ft.Text("Why ICESTONE SOFTWARE", size=16, weight=ft.FontWeight.BOLD, color=dark_blue),
                                            ft.Text("➤ 24/7 Service and support.", size=12, color=text_color_dark),
                                            ft.Text("➤ Locally and Known Business person", size=12, color=text_color_dark),
                                            ft.Text("➤ Software available with ANDROID APPLICATION", size=12, color=text_color_dark),
                                            ft.Text("➤ Service and support @ YOUR DOOR STEP", size=12, color=text_color_dark),
                                            ft.Text("➤ Fully customized software and MULTI USER", size=12, color=text_color_dark),
                                            ft.Text("➤ Only need BASIC COMPUTER knowledge for software use", size=12, color=text_color_dark),
                                        ],
                                        spacing=2
                                    ),
                                    ft.Column(
                                        [
                                            ft.Text("Service & Supports", size=16, weight=ft.FontWeight.BOLD, color=dark_blue),
                                            ft.Text("+91 9898160983", size=12, color=text_color_dark),
                                            ft.Text("+91 9898160983", size=12, color=text_color_dark),
                                        ],
                                        spacing=2
                                    )
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_AROUND,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                            ),
                            width=page.window_width * 0.7,
                            padding=ft.padding.all(15),
                            border_radius=ft.border_radius.all(15),
                            bgcolor=card_background,
                            shadow=ft.BoxShadow(
                                spread_radius=1,
                                blur_radius=5,
                                color=ft.Colors.BLACK12, # Corrected: BLACK_12 to BLACK12
                                offset=ft.Offset(0, 2),
                            ),
                            gradient=glossy_gradient_light,
                            expand=True # Added expand=True to dashboard_content
                        )
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                    spacing=0,
                    expand=True
                ),
                # Right Section (Side Menu)
                ft.Container(
                    content=ft.Column(
                        [
                            ft.TextButton(content=ft.Text("Loan Application", size=14, weight=ft.FontWeight.BOLD, color=dark_blue), on_click=lambda e: page.go("/crm")),
                            ft.Divider(),
                            ft.TextButton(content=ft.Text("Party Master", size=14, weight=ft.FontWeight.BOLD, color=dark_blue), on_click=lambda e: page.go("/master")),
                            ft.Text("Reminder Master", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("Smart Search", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("Backup", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Divider(),
                            ft.Text("Cash Book", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("Bank Book", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("Journal Entry", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("Cheque Printing", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("Day Book", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Divider(),
                            ft.Text("Loan Summary", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("Recurring Entry", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("Rec. Int. Calcu.", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("Share Summary", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Divider(),
                            ft.Text("View Ledger", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("Statistic Report", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("P & L Statment", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Text("Balance Sheet", size=14, weight=ft.FontWeight.BOLD, color=dark_blue),
                            ft.Divider(),
                            ft.ElevatedButton(
                                "Open Anydesk",
                                icon=ft.Icons.DESKTOP_WINDOWS,
                                bgcolor=primary_gold,
                                color=text_color_dark,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                            ),
                        ],
                        spacing=10,
                        horizontal_alignment=ft.CrossAxisAlignment.START
                    ),
                    padding=ft.padding.all(15),
                    margin=ft.margin.only(left=20),
                    border_radius=ft.border_radius.all(15),
                    bgcolor=card_background,
                    shadow=ft.BoxShadow(
                        spread_radius=1,
                        blur_radius=5,
                        color=ft.Colors.BLACK12, # Corrected: BLACK_12 to BLACK12
                        offset=ft.Offset(0, 2),
                    ),
                    gradient=glossy_gradient_light,
                    width=200,
                    height=650,
                )
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=20,
            expand=True
        ),
        padding=ft.padding.all(20),
        bgcolor=light_grey_bg,
        expand=True
    )

    # --- Bottom Status Bar ---
    bottom_status = ft.Container(
        content=ft.Row(
            [
                ft.Text("Company : DEMO COMPANY", size=12, color=text_color_dark),
                ft.VerticalDivider(),
                ft.Text("Welcome : Administrator", size=12, color=text_color_dark),
                ft.VerticalDivider(),
                ft.Text("Year : 2020-2026", size=12, color=text_color_dark),
                ft.VerticalDivider(),
                ft.Text("Insert : Calculator", size=12, color=text_color_dark),
                ft.VerticalDivider(),
                ft.Text("Date : 05-Jul-2025", size=12, color=text_color_dark),
                ft.VerticalDivider(),
                ft.Text("Time : 02:25:18 PM", size=12, color=text_color_dark),
                ft.VerticalDivider(),
                ft.Row([
                    ft.IconButton(ft.Icons.AUTO_AWESOME, tooltip="I AUTO"),
                    ft.IconButton(ft.Icons.BACKUP, tooltip="Backup Option Disable For This Company."),
                    ft.IconButton(ft.Icons.REFRESH, tooltip="I RICE"),
                    ft.IconButton(ft.Icons.CREDIT_CARD, tooltip="I CRM"),
                    ft.IconButton(ft.Icons.PHONE_ANDROID, tooltip="I APP"),
                ], spacing=0)
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.padding.symmetric(horizontal=10, vertical=5),
        bgcolor=dark_blue,
        width=page.window_width,
        height=40,
        border_radius=ft.border_radius.vertical(top=5, bottom=0)
    )

    # --- New Page Views ---

    class MasterView(ft.Container):
        def __init__(self):
            super().__init__(
                content=ft.Column(
                    [
                        ft.Text("Master Data Management", size=24, weight=ft.FontWeight.BOLD, color=dark_blue),
                        ft.Divider(),
                        ft.Text("Here you can manage customer details, loan types, and other master data.", size=16, color=text_color_dark),
                        ft.ElevatedButton(
                            "Add New Customer",
                            icon=ft.Icons.PERSON_ADD,
                            bgcolor=dark_blue,
                            color=text_color_light,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                        ),
                        ft.ElevatedButton(
                            "Manage Loan Types",
                            icon=ft.Icons.MONEY,
                            bgcolor=dark_blue,
                            color=text_color_light,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                    spacing=20
                ),
                padding=ft.padding.all(30),
                margin=ft.margin.all(20),
                border_radius=ft.border_radius.all(15),
                bgcolor=card_background,
                shadow=ft.BoxShadow(
                    spread_radius=1,
                    blur_radius=10,
                    color=ft.Colors.BLACK12, # Corrected: BLACK_12 to BLACK12
                    offset=ft.Offset(0, 5),
                ),
                gradient=glossy_gradient_light,
                expand=True
            )

    class TransactionView(ft.Container):
        def __init__(self):
            super().__init__(
                content=ft.Column(
                    [
                        ft.Text("Loan Transactions", size=24, weight=ft.FontWeight.BOLD, color=dark_blue),
                        ft.Divider(),
                        ft.Text("Process new loans, repayments, and other financial transactions here.", size=16, color=text_color_dark),
                        ft.ElevatedButton(
                            "New Loan Application",
                            icon=ft.Icons.ADD_CIRCLE,
                            bgcolor=dark_blue,
                            color=text_color_light,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                        ),
                        ft.ElevatedButton(
                            "Process Repayment",
                            icon=ft.Icons.PAYMENT,
                            bgcolor=dark_blue,
                            color=text_color_light,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                    spacing=20
                ),
                padding=ft.padding.all(30),
                margin=ft.margin.all(20),
                border_radius=ft.border_radius.all(15),
                bgcolor=card_background,
                shadow=ft.BoxShadow(
                    spread_radius=1,
                    blur_radius=10,
                    color=ft.Colors.BLACK12, # Corrected: BLACK_12 to BLACK12
                    offset=ft.Offset(0, 5),
                ),
                gradient=glossy_gradient_light,
                expand=True
            )

    class AccountView(ft.Container):
        def __init__(self):
            super().__init__(
                content=ft.Column(
                    [
                        ft.Text("Account Management", size=24, weight=ft.FontWeight.BOLD, color=dark_blue),
                        ft.Divider(),
                        ft.Text("View account statements, ledgers, and manage financial records.", size=16, color=text_color_dark),
                        ft.ElevatedButton(
                            "View Account Statement",
                            icon=ft.Icons.RECEIPT,
                            bgcolor=dark_blue,
                            color=text_color_light,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                        ),
                        ft.ElevatedButton(
                            "Access Ledger",
                            icon=ft.Icons.BOOK,
                            bgcolor=dark_blue,
                            color=text_color_light,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                    spacing=20
                ),
                padding=ft.padding.all(30),
                margin=ft.margin.all(20),
                border_radius=ft.border_radius.all(15),
                bgcolor=card_background,
                shadow=ft.BoxShadow(
                    spread_radius=1,
                    blur_radius=10,
                    color=ft.Colors.BLACK12, # Corrected: BLACK_12 to BLACK12
                    offset=ft.Offset(0, 5),
                ),
                gradient=glossy_gradient_light,
                expand=True
            )

    class ReportView(ft.Container):
        def __init__(self):
            super().__init__(
                content=ft.Column(
                    [
                        ft.Text("Reports & Analytics", size=24, weight=ft.FontWeight.BOLD, color=dark_blue),
                        ft.Divider(),
                        ft.Text("Generate various reports for business insights.", size=16, color=text_color_dark),
                        ft.ElevatedButton(
                            "Loan Portfolio Report",
                            icon=ft.Icons.PIE_CHART,
                            bgcolor=dark_blue,
                            color=text_color_light,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                        ),
                        ft.ElevatedButton(
                            "Collection Summary",
                            icon=ft.Icons.COLLECTIONS_BOOKMARK,
                            bgcolor=dark_blue,
                            color=text_color_light,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                    spacing=20
                ),
                padding=ft.padding.all(30),
                margin=ft.margin.all(20),
                border_radius=ft.border_radius.all(15),
                bgcolor=card_background,
                shadow=ft.BoxShadow(
                    spread_radius=1,
                    blur_radius=10,
                    color=ft.Colors.BLACK12, # Corrected: BLACK_12 to BLACK12
                    offset=ft.Offset(0, 5),
                ),
                gradient=glossy_gradient_light,
                expand=True
            )

    class CrmGoldLoanView(ft.Container):
        def __init__(self):
            super().__init__(
                content=ft.Column(
                    [
                        ft.Text("Gold Loan CRM", size=28, weight=ft.FontWeight.BOLD, color=primary_gold),
                        ft.Divider(height=20, color=primary_gold),
                        ft.Row(
                            [
                                # Customer List / Search
                                ft.Container(
                                    content=ft.Column(
                                        [
                                            ft.Text("Existing Customers", size=18, weight=ft.FontWeight.BOLD, color=dark_blue),
                                            ft.TextField(label="Search Customer", icon=ft.Icons.SEARCH, border_radius=10),
                                            ft.ListView(
                                                [
                                                    ft.Text("John Doe - Loan #GL001", size=14),
                                                    ft.Text("Jane Smith - Loan #GL002", size=14),
                                                    ft.Text("Alice Johnson - Loan #GL003", size=14),
                                                    ft.Text("Bob Williams - Loan #GL004", size=14),
                                                ],
                                                expand=True,
                                                spacing=10,
                                                padding=ft.padding.symmetric(vertical=10)
                                            )
                                        ],
                                        spacing=10,
                                        horizontal_alignment=ft.CrossAxisAlignment.START
                                    ),
                                    padding=ft.padding.all(15),
                                    border_radius=ft.border_radius.all(15),
                                    bgcolor=card_background,
                                    shadow=ft.BoxShadow(
                                        spread_radius=1,
                                        blur_radius=5,
                                        color=ft.Colors.BLACK12, # Corrected: BLACK_12 to BLACK12
                                        offset=ft.Offset(0, 2),
                                    ),
                                    gradient=glossy_gradient_light,
                                    width=300,
                                    height=400
                                ),
                                # New Loan Application Form
                                ft.Container(
                                    content=ft.Column(
                                        [
                                            ft.Text("New Gold Loan Application", size=18, weight=ft.FontWeight.BOLD, color=dark_blue),
                                            ft.TextField(label="Customer Name", border_radius=10),
                                            ft.TextField(label="Contact Number", border_radius=10),
                                            ft.TextField(label="Gold Weight (grams)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=10),
                                            ft.TextField(label="Gold Purity (Karat)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=10),
                                            ft.TextField(label="Loan Amount Requested", keyboard_type=ft.KeyboardType.NUMBER, border_radius=10),
                                            ft.ElevatedButton(
                                                "Submit Loan Application",
                                                icon=ft.Icons.CHECK_CIRCLE,
                                                bgcolor=primary_gold,
                                                color=text_color_dark,
                                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                                            ),
                                        ],
                                        spacing=10,
                                        horizontal_alignment=ft.CrossAxisAlignment.START
                                    ),
                                    padding=ft.padding.all(15),
                                    border_radius=ft.border_radius.all(15),
                                    bgcolor=card_background,
                                    shadow=ft.BoxShadow(
                                        spread_radius=1,
                                        blur_radius=5,
                                        color=ft.Colors.BLACK12, # Corrected: BLACK_12 to BLACK12
                                        offset=ft.Offset(0, 2),
                                    ),
                                    gradient=glossy_gradient_light,
                                    width=350,
                                    height=400
                                ),
                                # Gold Valuation Calculator & Loan Status
                                ft.Container(
                                    content=ft.Column(
                                        [
                                            ft.Text("Gold Valuation Calculator", size=18, weight=ft.FontWeight.BOLD, color=dark_blue),
                                            ft.TextField(label="Weight (grams)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=10),
                                            ft.TextField(label="Purity (Karat)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=10),
                                            ft.ElevatedButton(
                                                "Calculate Value",
                                                icon=ft.Icons.CALCULATE,
                                                bgcolor=dark_blue,
                                                color=text_color_light,
                                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                                            ),
                                            ft.Text("Estimated Value: ₹ 0.00", size=16, weight=ft.FontWeight.BOLD, color=primary_gold),
                                            ft.Divider(),
                                            ft.Text("Loan Status & Tracking", size=18, weight=ft.FontWeight.BOLD, color=dark_blue),
                                            ft.Text("Selected Loan: None", size=14),
                                            ft.Text("Status: Pending", size=14),
                                            ft.Text("Next Action: Follow-up", size=14),
                                        ],
                                        spacing=10,
                                        horizontal_alignment=ft.CrossAxisAlignment.START
                                    ),
                                    padding=ft.padding.all(15),
                                    border_radius=ft.border_radius.all(15),
                                    bgcolor=card_background,
                                    shadow=ft.BoxShadow(
                                        spread_radius=1,
                                        blur_radius=5,
                                        color=ft.Colors.BLACK12, # Corrected: BLACK_12 to BLACK12
                                        offset=ft.Offset(0, 2),
                                    ),
                                    gradient=glossy_gradient_light,
                                    width=350,
                                    height=400
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_AROUND,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                            wrap=True,
                            expand=True
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=20,
                    expand=True
                ),
                padding=ft.padding.all(20),
                bgcolor=light_grey_bg,
                expand=True
            )

    # Initial page content
    page.add(
        top_nav,
        dashboard_content, # Removed ft.Expanded here as dashboard_content now has expand=True
        bottom_status
    )
    page.go(page.route) # Go to the initial route to render the view

ft.app(target=main)
