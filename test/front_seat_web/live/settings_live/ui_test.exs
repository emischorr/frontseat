defmodule FrontSeatWeb.SettingsLive.UiTest do
  use FrontSeatWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  alias FrontSeat.Accounts

  @moduletag role: :admin

  setup :register_and_log_in_user

  test "defaults to off", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/settings/ui")

    refute view
           |> element("#ui-form input[type=checkbox][name=\"ui[show_cost_on_cards]\"]")
           |> render() =~ "checked"
  end

  test "turns on cost display on task cards", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/settings/ui")

    view
    |> form("#ui-form", ui: %{show_cost_on_cards: "true"})
    |> render_submit()

    assert Accounts.get_ui_settings() == %{show_cost_on_cards: true}
  end

  test "turns it back off", %{conn: conn, scope: scope} do
    {:ok, _} = Accounts.update_ui_settings(scope, %{"show_cost_on_cards" => "true"})
    {:ok, view, _html} = live(conn, ~p"/settings/ui")

    view
    |> form("#ui-form", ui: %{show_cost_on_cards: "false"})
    |> render_submit()

    assert Accounts.get_ui_settings() == %{show_cost_on_cards: false}
  end
end
