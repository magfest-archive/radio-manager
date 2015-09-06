from termcolor import cprint, colored
import functools
import readline
import json
import time
import sys

CONFIG = {}

LIMITS = {}

UNLIMITED = None

CHECKED_IN = 'CHECKED_IN'
CHECKED_OUT = 'CHECKED_OUT'

ALLOW_MISSING_HEADSET = 'ALLOW_MISSING_HEADSET'
ALLOW_EXTRA_HEADSET = 'ALLOW_EXTRA_HEADSET'

ALLOW_DOUBLE_CHECKOUT = 'ALLOW_DOUBLE_CHECKOUT'
ALLOW_DOUBLE_RETURN = 'ALLOW_DOUBLE_RETURN'

ALLOW_NEGATIVE_HEADSETS = 'ALLOW_NEGATIVE_HEADSETS'

ALLOW_DEPARTMENT_OVERDRAFT = 'ALLOW_DEPARTMENT_OVERDRAFT'

RADIOS = {}

AUDIT_LOG = []

HEADSETS = 0

class RadioNotFound(Exception):
    pass

class RadioUnavailable(Exception):
    pass

class HeadsetUnavailable(Exception):
    pass

class HeadsetRequired(Exception):
    pass

class UnexpectedHeadset(Exception):
    pass

class NotCheckedOut(Exception):
    pass

class DepartmentOverLimit(Exception):
    pass

def load_db():
    data = {}
    try:
        with open(CONFIG['db']) as f:
            data = json.load(f)
        global HEADSETS, AUDIT_LOG

        RADIOS.update(data.get('radios', {}))

        HEADSETS = data.get('headsets', 0)
        AUDIT_LOG = data.get('audits', [])
    except FileNotFoundError:
        with open(CONFIG['db'], 'w') as f:
            json.dump({}, f)

def save_db():
    with open(CONFIG['db'], 'w') as f:
        json.dump({'radios': RADIOS, 'headsets': HEADSETS, 'audits': AUDIT_LOG}, f)

def apply_audit(override, radio, borrower, lender, description=''):
    AUDIT_LOG.append({
        'time': time.time(),
        'radio': radio,
        'borrower': borrower,
        'lender': lender,
        'type': override,
        'description': description,
    })

def department_total(dept):
    radio_count = 0
    headset_count = 0
    for radio in RADIOS.values():
        if radio['status'] == CHECKED_OUT and \
           radio['checkout']['department'] == dept:
            radio_count += 1
            if radio['headset']:
                headset_count += 1
    return (radio_count, headset_count)

def checkout_radio(id, dept, name=None, badge=None, headset=False, overrides=[]):
    global HEADSETS
    try:
        radio = RADIOS[id]

        if radio['status'] == CHECKED_OUT and \
           ALLOW_DOUBLE_CHECKOUT not in overrides:
            raise RadioUnavailable("Already checked out")

        if headset and HEADSETS == 0 and \
           ALLOW_NEGATIVE_HEADSETS not in overrides:
            raise HeadsetUnavailable("No headsets left")

        if dept not in LIMITS or \
           (LIMITS[dept] != UNLIMITED and
            department_total(dept)[1] >= LIMITS[dept]) and \
            ALLOW_DEPARTMENT_OVERDRAFT not in overrides:
            raise DepartmentOverLimit("Department would exceed checkout limit")

        radio['status'] = CHECKED_OUT
        radio['last_activity'] = time.time()
        radio['checkout'] = {
            'status': radio['status'],
            'time': radio['last_activity'],
            'borrower': name,
            'department': dept,
            'badge': badge,
            'headset': headset,
        }
        radio['history'].append(radio['checkout'])

        if headset:
            HEADSETS -= 1

        save_db()
    except IndexError:
        raise RadioNotFound("Radio does not exist")

def return_radio(id, headset=False, overrides=[]):
    try:
        radio = RADIOS[id]

        if radio['status'] == CHECKED_IN and \
           ALLOW_DOUBLE_CHECKIN not in overrides:
            raise AlreadyCheckedIn("Radio was already checked in")

        if radio['checkout']['headset'] and not headset and \
           ALLOW_MISSING_HEADSET not in overrides:
            raise HeadsetRequired("Radio was checked out with headset")
        elif headset and not radio['checkout']['headset'] and \
             ALLOW_EXTRA_HEADSET not in overrides:
            raise UnexpectedHeadset("Radio was not checked out with headset")

        radio['status'] = CHECKED_IN
        radio['last_activity'] = time.time()

        radio['checkout'] = {
            'status': radio['status'],
            'time': radio['last_activity'],
            'borrower': None,
            'department': None,
            'badge': None,
            'headset': None,
        }

        radio['history'].append(radio['checkout'])

        if headset:
            global HEADSETS
            HEADSETS += 1
        
    except IndexError:
        raise RadioNotFound("Radio does not exist")

def configure(f):
    with open(f) as conf:
        CONFIG.update(json.load(conf))

    load_db()

    for radio in CONFIG.get('radios', []):
        if radio not in RADIOS:
            RADIOS[radio] = {
                'status': CHECKED_IN,
                'last_activity': 0,
                'history': [{'status': CHECKED_IN,
                             'department': None,
                             'borrower': None,
                             'badge': None,
                             'headset': None,
                             'time': 0,
                }],
                'checkout': {
                    'status': CHECKED_IN,
                    'department': None,
                    'borrower': None,
                    'badge': None,
                    'headset': None,
                    'time': 0,
                },
            }

    for name, dept in CONFIG.get('departments', {}).items():
        LIMITS[name] = dept.get('limit', UNLIMITED)

def get_value(prompt, errmsg, completer=None, options=None, validator=None, fix=None, fixmsg=None):
    if callable(options):
        options = options()

    value = None

    while True:
        readline.set_completer(completer)
        value = input(prompt)

        if (not options or value in options) and \
           (not validator or validator(value)):
            return value
        else:
            cprint(errmsg, 'red')
            if fix:
                if fixmsg:
                    do_fix = get_value(colored(fixmsg, 'yellow'), 'Please enter \'y\' or \'n\'.', validator=lambda v: v and v.lower()[:1] in ('y', 'n'))
                    if do_fix.startswith('y'):
                        fix(value)
                        return value
                else:
                    fix(value)
                    return value

def add_dept(name):
    LIMITS[name] = {'limit': None}

def complete(items, text, state):
    valid = [item for item in (items() if callable(items) else items) if any((
        word.lower().startswith(text.lower()) for word in item.split()))]

    if valid:
        return valid[state][valid[state].lower().find(text.lower()):]

def add_radio(id):
    if id not in RADIOS:
        RADIOS[id] = {
            'status': CHECKED_IN,
            'last_activity': 0,
            'history': [{'status': CHECKED_IN,
                         'department': None,
                         'borrower': None,
                         'badge': None,
                         'headset': None,
                         'time': 0,
            }],
            'checkout': {
                'status': CHECKED_IN,
                'department': None,
                'borrower': None,
                'badge': None,
                'headset': None,
                'time': 0,
            },
        }

complete_dept = functools.partial(complete, LIMITS.keys)
complete_person = functools.partial(complete, [
    hist['borrower'] for radio in RADIOS.values() for hist in radio.get('history', []) if hist['borrower']])
complete_in_radios = functools.partial(complete, lambda: [str(k) for k,v in RADIOS.items() if v['status'] == CHECKED_IN])
complete_out_radios = functools.partial(complete, lambda: [str(k) for k,v in RADIOS.items() if v['status'] == CHECKED_OUT])
complete_radios = functools.partial(complete, lambda: [str(k) for k in RADIOS.keys()])

get_bool = lambda q: get_value(prompt=q, errmsg='Please enter \'y\' or \'n\'.', validator=lambda v: v and v.lower()[:1] in ('y', 'n')).lower().startswith('y')
get_headset = functools.partial(get_bool, 'Headset? (y/n) ')
get_radio = functools.partial(get_value, 'Radio ID: ', 'Radio does not exist!', complete_in_radios, lambda: [str(k) for k in RADIOS], fix=add_radio, fixmsg='Add this radio? (y/n) ')
get_person = functools.partial(get_value, 'Borrower (skip for department): ', 'Enter a name!', complete_person)
get_dept = functools.partial(get_value, 'Department: ', 'That department does not exist!', complete_dept, LIMITS.keys, fix=add_dept, fixmsg='Add new department? ')

def lookup_badge(number):
    raise NotImplementedError()

def confirm_except(e):
    return get_bool(colored(str(e), 'red', attrs=['bold']) + ' -- Continue anyway? ')

def do_checkout():
    args = (get_radio(), get_dept())
    kwargs = {'headset': get_headset()}
    who = get_person()
    if who.isnumeric():
        try:
            name = lookup_badge(who)
            kwargs['name'] = name
            kwargs['badge'] = who
        except:
            kwargs['badge'] = who
            kwargs['name'] = None
    else:
        kwargs['name'] = who
        kwargs['badge'] = None
    overrides = []
    while True:
        try:
            checkout_radio(*args, overrides=overrides, **kwargs)
            cprint('Checked out Radio #{} to {}'.format(args[0], kwargs['name']), 'green')
            return True
        except RadioNotFound as e:
            if confirm_except(e):
                add_radio(args[0])
            else:
                return False
        except OverrideException as e:
            if confirm_except(e):
                overrides.append(e.override)
            else:
                return False

def do_checkin():
    args = (get_radio(), get_headset())
    overrides=[]

    while True:
        try:
            return_radio(*args, overrides=overrides)
            cprint('Radio #{} returned by {}'.format(args[0], kwargs['name']), 'green')
            return True
        except OverrideException as e:
            if get_bool(colored(str(e), 'red') + "; Check out anyway?"):
                overrides.append(override)
            else:
                return False

def main_menu():
    cprint("===== Actions =====", 'blue')
    print(" {}. Check Out Radio".format(colored('1', 'cyan')))
    print(" {}. Check In Radio".format(colored('2', 'cyan')))
    print(" {}. Show Help".format(colored('?', 'cyan')))
    print(" {}. Exit".format(colored('X', 'cyan')))
    print()
    cprint("You can use Tab to auto-complete options for most fields", attrs=['bold'])
    print("Press " + colored('Ctrl+C', 'red') + ' to cancel any action and return to the menu.')
    return True

ACTIONS = {
    "Check out": do_checkout,
    "Check in": do_checkin,
    "Return": do_checkin,
    "1": do_checkout,
    "2": do_checkin,
    "X": sys.exit,
    "Q": sys.exit,
    "x": sys.exit,
    "q": sys.exit,
    "ci": do_checkin,
    "co": do_checkout,
    "?": main_menu,
    '': main_menu,
}

complete_actions = functools.partial(complete, ACTIONS.keys)
get_action = functools.partial(get_value, '> ', 'Action not found. Type \'?\' for help.', complete_actions, options=ACTIONS.keys)

def main():
    configure('config.json')
    readline.parse_and_bind('tab: complete')
    main_menu()

    while True:
        try:
            while True:
                action = get_action()
                try:
                    if ACTIONS[action]():
                        pass
                    else:
                        print()
                        cprint('Canceled', 'yellow')
                except KeyboardInterrupt:
                    print()
                    cprint('Canceled', 'yellow')
        except KeyboardInterrupt:
            print()
            cprint('Type \'X\' to exit.', 'yellow')

if __name__ == '__main__':
    main()
