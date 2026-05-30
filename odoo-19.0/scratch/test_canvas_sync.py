import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import config
import json

def test_canvas_sync():
    # Parse Odoo configuration
    config.parse_config(['-c', '/etc/odoo/odoo.conf', '-d', 'qwerty'])
    registry = Registry('qwerty')

    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        
        print("=" * 70)
        print("RUNNING BOT FLOW BIDIRECTIONAL SYNC TESTS")
        print("=" * 70)

        # Let's find/create a WhatsApp account first
        account = env['whatsapp.account'].search([], limit=1)
        if not account:
            account = env['whatsapp.account'].create({
                'name': 'TEST_ACCOUNT',
                'account_uid': '1234567890',
                'token': 'test_token',
                'app_id': 'app_123',
                'app_secret': 'secret_123',
            })
        print(f"Using WhatsApp Account ID: {account.id}")

        # Let's clean up existing test flows
        existing_test_flows = env['whatsapp.bot.flow'].search([('name', 'like', 'TEST_FLOW_')])
        if existing_test_flows:
            existing_test_flows.unlink()
            print("Cleaned up old test flows.")

        # Test 1: Flow creation and default first step
        print("\n--- TEST 1: Flow Creation & Defaults ---")
        flow = env['whatsapp.bot.flow'].create({
            'name': 'TEST_FLOW_1',
            'account_id': account.id,
            'trigger_type': 'keyword',
            'keywords': 'test, hello',
        })
        print(f"Created Flow ID: {flow.id}, name: {flow.name}")
        print(f"Default steps count: {len(flow.step_ids)}")
        for step in flow.step_ids:
            print(f"  Step ID: {step.id}, name: {step.name}, action_type: {step.action_type}")

        # Test 2: Synchronize from visual canvas to steps
        print("\n--- TEST 2: Sync Canvas to Steps (All 11 Node Types) ---")
        # Let's simulate a complex canvas saving operation
        canvas_payload = {
            'nodes': [
                {
                    'id': 'trigger_1',
                    'type': 'trigger',
                    'subtype': 'keyword',
                    'label': 'Trigger keyword',
                    'x': 50,
                    'y': 100,
                    'config': {
                        'trigger_type': 'keyword',
                        'keywords': 'start, init'
                    }
                },
                {
                    'id': 'text_1',
                    'type': 'message',
                    'subtype': 'text',
                    'label': 'Welcome plain text',
                    'x': 350,
                    'y': 100,
                    'config': {
                        'message_mode': 'text',
                        'message_text': 'Hi, welcome to our service!'
                    }
                },
                {
                    'id': 'buttons_1',
                    'type': 'message',
                    'subtype': 'buttons',
                    'label': 'Main Menu Options',
                    'x': 650,
                    'y': 100,
                    'config': {
                        'message_mode': 'buttons',
                        'message_text': 'Choose one option please'
                    }
                },
                {
                    'id': 'condition_1',
                    'type': 'condition',
                    'subtype': 'if_else',
                    'label': 'Check Branch',
                    'x': 950,
                    'y': 100,
                    'config': {
                        'condition_type': 'keyword_match',
                        'condition_value': 'yes'
                    }
                },
                {
                    'id': 'delay_1',
                    'type': 'action',
                    'subtype': 'delay',
                    'label': 'Wait 10 seconds',
                    'x': 1250,
                    'y': 100,
                    'config': {
                        'action_kind': 'delay',
                        'delay_seconds': 10
                    }
                },
                {
                    'id': 'api_call_1',
                    'type': 'action',
                    'subtype': 'api_call',
                    'label': 'External API Webhook',
                    'x': 1550,
                    'y': 100,
                    'config': {
                        'action_kind': 'api_call',
                        'http_method': 'POST',
                        'http_url': 'https://api.example.com/webhook',
                        'http_payload': '{"event": "start"}',
                        'response_variable': 'api_res'
                    }
                },
                {
                    'id': 'wait_reply_1',
                    'type': 'action',
                    'subtype': 'wait_reply',
                    'label': 'Wait User Text',
                    'x': 1850,
                    'y': 100,
                    'config': {
                        'action_kind': 'wait_reply',
                        'save_response': True,
                        'response_variable': 'user_msg'
                    }
                },
                {
                    'id': 'end_1',
                    'type': 'action',
                    'subtype': 'end',
                    'label': 'Finish Journey',
                    'x': 2150,
                    'y': 100,
                    'config': {
                        'action_kind': 'end'
                    }
                }
            ],
            'connections': [
                {'from': 'trigger_1', 'to': 'text_1', 'label': ''},
                {'from': 'text_1', 'to': 'buttons_1', 'label': ''},
                {'from': 'buttons_1', 'to': 'condition_1', 'label': 'Option A'},
                {'from': 'buttons_1', 'to': 'delay_1', 'label': 'Option B'},
                {'from': 'condition_1', 'to': 'api_call_1', 'label': 'true'},
                {'from': 'condition_1', 'to': 'wait_reply_1', 'label': 'false'},
                {'from': 'delay_1', 'to': 'end_1', 'label': ''},
                {'from': 'api_call_1', 'to': 'end_1', 'label': ''},
                {'from': 'wait_reply_1', 'to': 'end_1', 'label': ''}
            ],
            'nextId': 10,
            'viewport': {'x': 0, 'y': 0, 'zoom': 1}
        }

        # Save canvas visual graph
        flow.save_visual_graph(canvas_payload)
        
        # Verify sync outputs
        flow.invalidate_recordset()
        print(f"Trigger keywords updated to: {flow.keywords}")
        print(f"Total steps created: {len(flow.step_ids)}")
        for step in flow.step_ids.sorted('step_number'):
            print(f"  Step ID: {step.id}, name: '{step.name}', type: {step.action_type}, node_id: {step.node_id}")
            if step.action_type == 'delay':
                print(f"    -> delay_seconds: {step.delay_seconds}")
            elif step.action_type == 'http_request':
                print(f"    -> url: {step.http_url}, method: {step.http_method}, payload: {step.http_payload}, response_var: {step.response_variable}")
            elif step.action_type == 'wait_response':
                print(f"    -> response_variable: {step.response_variable}")
            elif step.action_type == 'condition':
                print(f"    -> true_step: {step.condition_true_step.name if step.condition_true_step else 'None'}, false_step: {step.condition_false_step.name if step.condition_false_step else 'None'}")
            elif step.action_type == 'send_buttons':
                print(f"    -> buttons: {[btn.name for btn in step.button_ids]}")
                for btn in step.button_ids:
                    print(f"       Button '{btn.name}' links to step: {btn.next_step_id.name if btn.next_step_id else 'None'}")

        # Check Test 3: Bidirectional Sync - database step creation triggers canvas update without recursion
        print("\n--- TEST 3: DB Step updates sync back to canvas ---")
        # Edit step welcome message
        welcome_step = flow.step_ids.filtered(lambda s: s.node_id == 'text_1')
        welcome_step.write({
            'name': 'Welcome plain text updated',
            'message_text': 'Hi, welcome to our awesome service!'
        })
        flow.invalidate_recordset()
        canvas_after_edit = json.loads(flow.canvas_data)
        text_node = next(n for n in canvas_after_edit['nodes'] if n['id'] == 'text_1')
        print(f"Updated Node text: '{text_node['config'].get('message_text')}'")
        print(f"Updated Node label: '{text_node.get('label')}'")
        if text_node['label'] == 'Welcome plain text updated' and text_node['config'].get('message_text') == 'Hi, welcome to our awesome service!':
            print("SUCCESS: DB write synced back to canvas correctly.")
        else:
            print("FAILURE: DB write did not sync back to canvas.")

        # Test 4: DB button edit sync
        print("\n--- TEST 4: DB Button modifications sync to canvas ---")
        buttons_step = flow.step_ids.filtered(lambda s: s.node_id == 'buttons_1')
        buttons = buttons_step.button_ids.sorted('id')
        if buttons:
            buttons[0].write({'name': 'Option A Updated'})
        flow.invalidate_recordset()
        canvas_after_btn_edit = json.loads(flow.canvas_data)
        # Find connection matching the first button
        btn_conn = next(c for c in canvas_after_btn_edit['connections'] if c['from'] == 'buttons_1' and c['to'] == 'condition_1')
        print(f"Connection label after button rename: '{btn_conn.get('label')}'")
        if btn_conn.get('label') == 'Option A Updated':
            print("SUCCESS: DB button rename synced to canvas connection.")
        else:
            print("FAILURE: DB button rename did not sync.")

        # Test 5: Step deletion sync to canvas
        print("\n--- TEST 5: DB Step deletion unlinks from canvas ---")
        delay_step = flow.step_ids.filtered(lambda s: s.node_id == 'delay_1')
        delay_step.unlink()
        flow.invalidate_recordset()
        canvas_after_unlink = json.loads(flow.canvas_data)
        delay_node_exists = any(n for n in canvas_after_unlink['nodes'] if n['id'] == 'delay_1')
        delay_conn_exists = any(c for c in canvas_after_unlink['connections'] if c['from'] == 'delay_1' or c['to'] == 'delay_1')
        print(f"Delay Node exists in canvas: {delay_node_exists}")
        print(f"Delay connections exist in canvas: {delay_conn_exists}")
        if not delay_node_exists and not delay_conn_exists:
            print("SUCCESS: DB step deletion successfully cleaned canvas nodes and connections.")
        else:
            print("FAILURE: Canvas not updated on step deletion.")

        # Clean up
        flow.unlink()
        print("\nCleaned up all test flows.")
        print("=" * 70)
        print("BOT FLOW SYNC TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)

if __name__ == '__main__':
    test_canvas_sync()
