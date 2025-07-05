import flet as ft

def main(page: ft.Page):
    def login_clicked(e):
        username = username_field.value
        password = password_field.value
        if username == "admin" and password == "password":
            status_text.value = "✅ Login successful"
            status_text.color = "green"
        else:
            status_text.value = "❌ Invalid credentials"
            status_text.color = "red"
        page.update()

    page.title = "Login Page"
    page.theme_mode = "light"
    
    username_field = ft.TextField(label="Username", width=300)
    password_field = ft.TextField(label="Password", password=True, can_reveal_password=True, width=300)
    login_button = ft.ElevatedButton(text="Login", on_click=login_clicked)
    status_text = ft.Text(value="", size=16)

    page.add(
        ft.Column(
            [
                ft.Text("Please log in", size=24, weight="bold"),
                username_field,
                password_field,
                login_button,
                status_text
            ],
            alignment="center",
            horizontal_alignment="center"
        )
    )

ft.app(target=main)