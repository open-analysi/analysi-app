"""Unit tests for Microsoft Exchange On-Premises EWS integration actions."""

from unittest.mock import AsyncMock, patch

import pytest

from analysi.integrations.framework.integrations.exchange_onprem.actions import (
    CopyEmailAction,
    DeleteEmailAction,
    GetEmailAction,
    HealthCheckAction,
    LookupEmailAction,
    MoveEmailAction,
    RunQueryAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def base_credentials():
    """Base credentials for Exchange."""
    return {
        "username": "testuser@example.com",
        "password": "testpassword",
    }


@pytest.fixture
def base_settings():
    """Base settings for Exchange."""
    return {
        "url": "https://mail.example.com/EWS/Exchange.asmx",
        "version": "2016",
        "verify_server_cert": True,
        "timeout": 30,
        "use_impersonation": False,
    }


@pytest.fixture
def health_check_action(base_credentials, base_settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction(
        integration_id="exchange_onprem",
        action_id="health_check",
        settings=base_settings,
        credentials=base_credentials,
    )


@pytest.fixture
def lookup_email_action(base_credentials, base_settings):
    """Create LookupEmailAction instance."""
    return LookupEmailAction(
        integration_id="exchange_onprem",
        action_id="lookup_email",
        settings=base_settings,
        credentials=base_credentials,
    )


@pytest.fixture
def run_query_action(base_credentials, base_settings):
    """Create RunQueryAction instance."""
    return RunQueryAction(
        integration_id="exchange_onprem",
        action_id="run_query",
        settings=base_settings,
        credentials=base_credentials,
    )


@pytest.fixture
def get_email_action(base_credentials, base_settings):
    """Create GetEmailAction instance."""
    return GetEmailAction(
        integration_id="exchange_onprem",
        action_id="get_email",
        settings=base_settings,
        credentials=base_credentials,
    )


@pytest.fixture
def delete_email_action(base_credentials, base_settings):
    """Create DeleteEmailAction instance."""
    return DeleteEmailAction(
        integration_id="exchange_onprem",
        action_id="delete_email",
        settings=base_settings,
        credentials=base_credentials,
    )


@pytest.fixture
def move_email_action(base_credentials, base_settings):
    """Create MoveEmailAction instance."""
    return MoveEmailAction(
        integration_id="exchange_onprem",
        action_id="move_email",
        settings=base_settings,
        credentials=base_credentials,
    )


@pytest.fixture
def copy_email_action(base_credentials, base_settings):
    """Create CopyEmailAction instance."""
    return CopyEmailAction(
        integration_id="exchange_onprem",
        action_id="copy_email",
        settings=base_settings,
        credentials=base_credentials,
    )


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = {
        "s:Envelope": {
            "s:Body": {
                "m:ResolveNamesResponse": {
                    "m:ResponseMessages": {
                        "m:ResolveNamesResponseMessage": {"@ResponseClass": "Success"}
                    }
                }
            }
        }
    }

    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.return_value = mock_response

        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert "ews_version" in result["data"]
    mock_request.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="exchange_onprem",
        action_id="health_check",
        settings={},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_invalid_version():
    """Test health check with invalid EWS version."""
    action = HealthCheckAction(
        integration_id="exchange_onprem",
        action_id="health_check",
        settings={
            "url": "https://mail.example.com/EWS/Exchange.asmx",
            "version": "invalid",
        },
        credentials={
            "username": "testuser",
            "password": "testpass",
        },
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Invalid EWS version" in result["error"]


@pytest.mark.asyncio
async def test_health_check_connection_error(health_check_action):
    """Test health check with connection error."""
    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.side_effect = Exception("Connection failed")

        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert "Connection failed" in result["error"]
    assert result["data"]["healthy"] is False


# ============================================================================
# LOOKUP EMAIL ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_lookup_email_success(lookup_email_action):
    """Test successful email lookup."""
    mock_response = {
        "s:Envelope": {
            "s:Body": {
                "m:ResolveNamesResponse": {
                    "m:ResponseMessages": {
                        "m:ResolveNamesResponseMessage": {
                            "m:ResolutionSet": {
                                "t:Resolution": {
                                    "t:Mailbox": {
                                        "t:Name": "Test User",
                                        "t:EmailAddress": "test@example.com",
                                        "t:RoutingType": "SMTP",
                                        "t:MailboxType": "Mailbox",
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.return_value = mock_response

        result = await lookup_email_action.execute(email="test@example.com")

    assert result["status"] == "success"
    assert result["email"] == "test@example.com"
    assert result["resolved_count"] == 1
    assert len(result["resolutions"]) == 1
    assert result["resolutions"][0]["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_lookup_email_missing_parameter(lookup_email_action):
    """Test lookup email with missing email parameter."""
    result = await lookup_email_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "email" in result["error"]


@pytest.mark.asyncio
async def test_lookup_email_missing_credentials():
    """Test lookup email with missing credentials."""
    action = LookupEmailAction(
        integration_id="exchange_onprem",
        action_id="lookup_email",
        settings={},
        credentials={},
    )

    result = await action.execute(email="test@example.com")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_lookup_email_multiple_resolutions(lookup_email_action):
    """Test lookup email with multiple resolutions."""
    mock_response = {
        "s:Envelope": {
            "s:Body": {
                "m:ResolveNamesResponse": {
                    "m:ResponseMessages": {
                        "m:ResolveNamesResponseMessage": {
                            "m:ResolutionSet": {
                                "t:Resolution": [
                                    {
                                        "t:Mailbox": {
                                            "t:Name": "User 1",
                                            "t:EmailAddress": "user1@example.com",
                                            "t:RoutingType": "SMTP",
                                            "t:MailboxType": "Mailbox",
                                        }
                                    },
                                    {
                                        "t:Mailbox": {
                                            "t:Name": "User 2",
                                            "t:EmailAddress": "user2@example.com",
                                            "t:RoutingType": "SMTP",
                                            "t:MailboxType": "Mailbox",
                                        }
                                    },
                                ]
                            }
                        }
                    }
                }
            }
        }
    }

    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.return_value = mock_response

        result = await lookup_email_action.execute(email="user@example.com")

    assert result["status"] == "success"
    assert result["resolved_count"] == 2
    assert len(result["resolutions"]) == 2


# ============================================================================
# RUN QUERY ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_run_query_success(run_query_action):
    """Test successful email query."""
    mock_response = {
        "s:Envelope": {
            "s:Body": {
                "m:FindItemResponse": {
                    "m:ResponseMessages": {
                        "m:FindItemResponseMessage": {
                            "m:RootFolder": {
                                "@TotalItemsInView": "2",
                                "t:Items": {
                                    "t:Message": [
                                        {
                                            "t:ItemId": {"@Id": "item1"},
                                            "t:Subject": "Test Subject 1",
                                            "t:From": {
                                                "t:Mailbox": {
                                                    "t:EmailAddress": "sender1@example.com"
                                                }
                                            },
                                            "t:InternetMessageId": "<msg1@example.com>",
                                            "t:DateTimeReceived": "2026-05-10T10:00:00Z",
                                        },
                                        {
                                            "t:ItemId": {"@Id": "item2"},
                                            "t:Subject": "Test Subject 2",
                                            "t:From": {
                                                "t:Mailbox": {
                                                    "t:EmailAddress": "sender2@example.com"
                                                }
                                            },
                                            "t:InternetMessageId": "<msg2@example.com>",
                                            "t:DateTimeReceived": "2026-05-10T11:00:00Z",
                                        },
                                    ]
                                },
                            }
                        }
                    }
                }
            }
        }
    }

    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.return_value = mock_response

        result = await run_query_action.execute(
            email="testuser@example.com", folder="Inbox"
        )

    assert result["status"] == "success"
    assert result["email"] == "testuser@example.com"
    assert result["folder"] == "Inbox"
    assert result["items_returned"] == 2
    assert len(result["emails"]) == 2
    assert result["emails"][0]["subject"] == "Test Subject 1"


@pytest.mark.asyncio
async def test_run_query_missing_parameter(run_query_action):
    """Test run query with missing email parameter."""
    result = await run_query_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "email" in result["error"]


@pytest.mark.asyncio
async def test_run_query_with_range(run_query_action):
    """Test run query with custom range."""
    mock_response = {
        "s:Envelope": {
            "s:Body": {
                "m:FindItemResponse": {
                    "m:ResponseMessages": {
                        "m:FindItemResponseMessage": {
                            "m:RootFolder": {
                                "@TotalItemsInView": "5",
                                "t:Items": {
                                    "t:Message": {
                                        "t:ItemId": {"@Id": "item1"},
                                        "t:Subject": "Test",
                                        "t:From": {
                                            "t:Mailbox": {
                                                "t:EmailAddress": "sender@example.com"
                                            }
                                        },
                                        "t:InternetMessageId": "<msg@example.com>",
                                        "t:DateTimeReceived": "2026-05-10T10:00:00Z",
                                    }
                                },
                            }
                        }
                    }
                }
            }
        }
    }

    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.return_value = mock_response

        result = await run_query_action.execute(
            email="testuser@example.com", folder="Inbox", range="0-4"
        )

    assert result["status"] == "success"
    assert result["items_returned"] == 1


# ============================================================================
# GET EMAIL ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_email_success(get_email_action):
    """Test successful get email."""
    mock_response = {
        "s:Envelope": {
            "s:Body": {
                "m:GetItemResponse": {
                    "m:ResponseMessages": {
                        "m:GetItemResponseMessage": {
                            "m:Items": {
                                "t:Message": {
                                    "t:ItemId": {"@Id": "item123"},
                                    "t:Subject": "Test Email",
                                    "t:From": {
                                        "t:Mailbox": {
                                            "t:EmailAddress": "sender@example.com"
                                        }
                                    },
                                    "t:Sender": {
                                        "t:Mailbox": {
                                            "t:EmailAddress": "sender@example.com"
                                        }
                                    },
                                    "t:InternetMessageId": "<msg123@example.com>",
                                    "t:Body": {
                                        "@BodyType": "HTML",
                                        "#text": "<html>Email body</html>",
                                    },
                                    "t:DateTimeReceived": "2026-05-10T10:00:00Z",
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.return_value = mock_response

        result = await get_email_action.execute(id="item123")

    assert result["status"] == "success"
    assert result["email"]["id"] == "item123"
    assert result["email"]["subject"] == "Test Email"
    assert result["email"]["body"] == "<html>Email body</html>"


@pytest.mark.asyncio
async def test_get_email_missing_parameter(get_email_action):
    """Test get email with missing id parameter."""
    result = await get_email_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "id" in result["error"]


# ============================================================================
# DELETE EMAIL ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_delete_email_success(delete_email_action):
    """Test successful delete email."""
    mock_response = {
        "s:Envelope": {
            "s:Body": {
                "m:DeleteItemResponse": {
                    "m:ResponseMessages": {
                        "m:DeleteItemResponseMessage": {"@ResponseClass": "Success"}
                    }
                }
            }
        }
    }

    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.return_value = mock_response

        result = await delete_email_action.execute(id="item123")

    assert result["status"] == "success"
    assert result["id"] == "item123"
    assert "deleted successfully" in result["message"]


@pytest.mark.asyncio
async def test_delete_email_missing_parameter(delete_email_action):
    """Test delete email with missing id parameter."""
    result = await delete_email_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "id" in result["error"]


@pytest.mark.asyncio
async def test_delete_email_soap_error(delete_email_action):
    """Test delete email with SOAP error."""
    mock_response = {
        "s:Envelope": {
            "s:Body": {
                "m:DeleteItemResponse": {
                    "m:ResponseMessages": {
                        "m:DeleteItemResponseMessage": {
                            "@ResponseClass": "Error",
                            "m:MessageText": "Item not found",
                        }
                    }
                }
            }
        }
    }

    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.return_value = mock_response

        result = await delete_email_action.execute(id="item123")

    assert result["status"] == "error"
    assert result["error_type"] == "SOAPError"
    assert "Item not found" in result["error"]


# ============================================================================
# MOVE EMAIL ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_move_email_success(move_email_action):
    """Test successful move email."""
    mock_response = {
        "s:Envelope": {
            "s:Body": {
                "m:MoveItemResponse": {
                    "m:ResponseMessages": {
                        "m:MoveItemResponseMessage": {
                            "@ResponseClass": "Success",
                            "m:Items": {
                                "t:Message": {"t:ItemId": {"@Id": "newitem123"}}
                            },
                        }
                    }
                }
            }
        }
    }

    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.return_value = mock_response

        result = await move_email_action.execute(id="item123", folder="folder456")

    assert result["status"] == "success"
    assert result["original_id"] == "item123"
    assert result["new_id"] == "newitem123"
    assert result["folder"] == "folder456"


@pytest.mark.asyncio
async def test_move_email_missing_parameters(move_email_action):
    """Test move email with missing parameters."""
    result = await move_email_action.execute(id="item123")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "folder" in result["error"]


# ============================================================================
# COPY EMAIL ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_copy_email_success(copy_email_action):
    """Test successful copy email."""
    mock_response = {
        "s:Envelope": {
            "s:Body": {
                "m:CopyItemResponse": {
                    "m:ResponseMessages": {
                        "m:CopyItemResponseMessage": {
                            "@ResponseClass": "Success",
                            "m:Items": {
                                "t:Message": {"t:ItemId": {"@Id": "copieditem123"}}
                            },
                        }
                    }
                }
            }
        }
    }

    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.return_value = mock_response

        result = await copy_email_action.execute(id="item123", folder="folder456")

    assert result["status"] == "success"
    assert result["original_id"] == "item123"
    assert result["new_id"] == "copieditem123"
    assert result["folder"] == "folder456"


@pytest.mark.asyncio
async def test_copy_email_missing_parameters(copy_email_action):
    """Test copy email with missing parameters."""
    result = await copy_email_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "id" in result["error"]


@pytest.mark.asyncio
async def test_copy_email_soap_error(copy_email_action):
    """Test copy email with SOAP error."""
    mock_response = {
        "s:Envelope": {
            "s:Body": {
                "m:CopyItemResponse": {
                    "m:ResponseMessages": {
                        "m:CopyItemResponseMessage": {
                            "@ResponseClass": "Error",
                            "m:MessageText": "Invalid folder",
                        }
                    }
                }
            }
        }
    }

    with patch(
        "analysi.integrations.framework.integrations.exchange_onprem.actions.make_ews_request",
        new_callable=AsyncMock,
    ) as mock_request:
        mock_request.return_value = mock_response

        result = await copy_email_action.execute(id="item123", folder="invalid")

    assert result["status"] == "error"
    assert result["error_type"] == "SOAPError"
    assert "Invalid folder" in result["error"]
