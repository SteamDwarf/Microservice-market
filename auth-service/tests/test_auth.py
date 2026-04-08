import asyncio

from httpx import AsyncClient


class TestAuthService:
    # --- ТЕСТЫ РЕГИСТРАЦИИ ---

    async def test_register_success(self, client: AsyncClient):
        response = await client.post(
            "/api/auth/register/",
            json={
                "username": "new_user",
                "email": "new@example.com",
                "password": "securepassword",
            },
        )

        assert response.status_code == 200

        data = response.json()

        assert data["username"] == "new_user"
        assert "id" in data
        assert float(data["balance"]) == 0.0

    async def test_register_duplicate_username(self, client: AsyncClient):
        user_data = {
            "username": "duplicate",
            "email": "1@ex.com",
            "password": "password123",
        }

        await client.post("/api/auth/register/", json=user_data)

        response = await client.post("/api/auth/register/", json=user_data)

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    # --- ТЕСТЫ АУТЕНТИФИКАЦИИ ---

    async def test_login_success(self, client: AsyncClient):
        await client.post(
            "/api/auth/register/",
            json={
                "username": "login_user",
                "email": "l@ex.com",
                "password": "password123",
            },
        )

        response = await client.post(
            "/api/auth/token/",
            json={"username": "login_user", "password": "password123"},
        )

        assert response.status_code == 200

        json_data = response.json()

        assert "access" in json_data
        assert "refresh" in json_data
        assert json_data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post(
            "/api/auth/register/",
            json={
                "username": "user",
                "email": "u@ex.com",
                "password": "password123",
            },
        )

        response = await client.post(
            "/api/auth/token/",
            json={"username": "user", "password": "wrongpassword"},
        )

        assert response.status_code == 401

    async def test_token_refresh_success(self, client: AsyncClient):
        await client.post(
            "/api/auth/register/",
            json={
                "username": "refresher",
                "email": "r@ex.com",
                "password": "password123",
            },
        )

        login_res = await client.post(
            "/api/auth/token/",
            json={"username": "refresher", "password": "password123"},
        )
        login_data = login_res.json()
        old_refresh_token = login_data["refresh"]

        await asyncio.sleep(1.1)

        response = await client.post(
            "/api/auth/token/refresh/", json={"refresh": old_refresh_token}
        )

        assert response.status_code == 200

        new_data = response.json()

        assert "access" in new_data

        assert new_data["access"] != login_data["access"]

    # --- ТЕСТЫ ПРОФИЛЯ ---

    async def test_get_profile_authenticated(self, client: AsyncClient):
        await client.post(
            "/api/auth/register/",
            json={
                "username": "p",
                "email": "p@ex.com",
                "password": "password123",
            },
        )
        login_res = await client.post(
            "/api/auth/token/",
            json={"username": "p", "password": "password123"},
        )
        token = login_res.json()["access"]
        response = await client.get(
            "/api/auth/profile/", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert response.json()["username"] == "p"

    async def test_get_profile_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/auth/profile/")
        assert response.status_code == 401

    async def test_get_profile_after_refresh(self, client: AsyncClient):
        await client.post(
            "/api/auth/register/",
            json={
                "username": "user2",
                "email": "u2@ex.com",
                "password": "password123",
            },
        )

        login_res = await client.post(
            "/api/auth/token/",
            json={"username": "user2", "password": "password123"},
        )
        refresh_token = login_res.json()["refresh"]

        await asyncio.sleep(1.1)

        refresh_res = await client.post(
            "/api/auth/token/refresh/", json={"refresh": refresh_token}
        )
        new_access_token = refresh_res.json()["access"]

        response = await client.get(
            "/api/auth/profile/",
            headers={"Authorization": f"Bearer {new_access_token}"},
        )

        assert response.status_code == 200
        assert response.json()["username"] == "user2"

    # --- ТЕСТЫ БАЛАНСА ---

    async def test_top_up_success(self, client: AsyncClient):
        await client.post(
            "/api/auth/register/",
            json={
                "username": "wallet",
                "email": "w@ex.com",
                "password": "password123",
            },
        )

        login = await client.post(
            "/api/auth/token/",
            json={"username": "wallet", "password": "password123"},
        )
        token = login.json()["access"]

        response = await client.post(
            "/api/auth/topup/",
            json={"amount": "100.50"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert float(response.json()["balance"]) == 100.50

    async def test_top_up_negative_amount(self, client: AsyncClient):
        await client.post(
            "/api/auth/register/",
            json={
                "username": "neg",
                "email": "n@ex.com",
                "password": "password123",
            },
        )

        login = await client.post(
            "/api/auth/token/",
            json={"username": "neg", "password": "password123"},
        )
        token = login.json()["access"]

        response = await client.post(
            "/api/auth/topup/",
            json={"amount": "-50.00"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422

    # --- ТЕСТ НА RACE CONDITION ---

    async def test_top_up_race_condition(self, client: AsyncClient):
        username = "race_condition_user"

        await client.post(
            "/api/auth/register/",
            json={
                "username": username,
                "email": "r@ex.com",
                "password": "password123",
            },
        )

        login = await client.post(
            "/api/auth/token/",
            json={"username": username, "password": "password123"},
        )
        token = login.json()["access"]
        headers = {"Authorization": f"Bearer {token}"}

        tasks = [
            client.post(
                "/api/auth/topup/", json={"amount": "5.00"}, headers=headers
            )
            for _ in range(20)
        ]

        responses = await asyncio.gather(*tasks)
        for r in responses:
            assert r.status_code == 200

        final_profile = await client.get("/api/auth/profile/", headers=headers)
        assert float(final_profile.json()["balance"]) == 100.00
