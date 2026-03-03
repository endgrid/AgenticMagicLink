from app import ChatRequest, ContractorAccessBackend


def test_happy_path_with_session_persistence():
    backend = ContractorAccessBackend()

    first = backend.chat(ChatRequest(message=''))
    sid = first.body['session_id']
    assert first.body['state'] == 'ASK_FUNCTIONS'
    assert first.body['response'] == 'Contractor Access Agent'
    assert first.set_cookies['session_id'] == sid

    second = backend.chat(
        ChatRequest(
            message='Read S3 reports, Review CloudWatch logs',
            headers={'x-session-id': sid},
        )
    )
    assert second.body['state'] == 'ASK_ACCOUNT'
    assert 'policy' in second.body
    assert len(second.body['policy']['Statement']) == 2

    third = backend.chat(ChatRequest(message='123456789012', headers={'x-session-id': sid}))
    assert third.body['state'] == 'RETURN_SCRIPT'
    assert 'aws sts assume-role' in third.body['script']
    assert '123456789012' in third.body['script']


def test_invalid_retries_for_functions_and_account_id():
    backend = ContractorAccessBackend()

    first = backend.chat(ChatRequest(message=''))
    sid = first.body['session_id']

    invalid_functions = backend.chat(ChatRequest(message='   ', headers={'x-session-id': sid}))
    assert invalid_functions.body['state'] == 'ASK_FUNCTIONS'
    assert 'non-empty contractor function' in invalid_functions.body['response']

    valid_functions = backend.chat(ChatRequest(message='Deploy release', headers={'x-session-id': sid}))
    assert valid_functions.body['state'] == 'ASK_ACCOUNT'

    invalid_account = backend.chat(ChatRequest(message='1234', headers={'x-session-id': sid}))
    assert invalid_account.body['state'] == 'ASK_ACCOUNT'
    assert '12-digit' in invalid_account.body['response']

    valid_account = backend.chat(ChatRequest(message='210987654321', headers={'x-session-id': sid}))
    assert valid_account.body['state'] == 'RETURN_SCRIPT'


def test_session_cookie_is_used_when_header_missing():
    backend = ContractorAccessBackend()

    first = backend.chat(ChatRequest(message=''))
    sid = first.set_cookies['session_id']

    second = backend.chat(ChatRequest(message='Write audit summary', cookies={'session_id': sid}))
    assert second.body['state'] == 'ASK_ACCOUNT'
