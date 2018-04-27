'''
Migrates revisions into the activity stream, to allow you to view old versions
of datasets and changes (diffs) between them.
'''

# This cost is not part of the main migrations because it takes a long time to
# run, and you don't want it to delay a site going live again after an upgrade.

# This code is not part of the main CKAN CLI because it is a one-off migration,
# whereas the main CLI is a list of tools for more frequent use.

import argparse

# not importing anything from ckan until after the arg parsing, to fail on bad
# args quickly.

_context = None


def get_context():
    from ckan import model
    import ckan.logic as logic
    global _context
    if not _context:
        user = logic.get_action('get_site_user')(
            {'model': model, 'ignore_auth': True}, {})
        _context = {'model': model, 'session': model.Session,
                    'user': user['name']}
    return _context


def migrate_all_datasets():
    import ckan.logic as logic
    dataset_names = logic.get_action('package_list')(get_context(), {})
    num_datasets = len(dataset_names)
    for i, dataset_name in enumerate(dataset_names):
        print '{}/{} {}'.format(i + 1, num_datasets, dataset_name)
        migrate_dataset(dataset_name)


def migrate_dataset(dataset_name):
    import ckan.logic as logic
    from ckan import model

    context = get_context()
    # 'hidden' activity is that by site_user, such as harvests, which are
    # not shown in the activity stream because they can be too numerous.
    # However thes do have Activity objects, and if a hidden Activity is
    # followed be a non-hidden one and you look at the changes of that
    # non-hidden Activity, then it does a diff with the hidden one (rather than
    # the most recent non-hidden one), so it is important to store the
    # package_dict in hidden Activity objects.
    context['include_hidden_activity'] = True
    package_activity_stream = logic.get_action('package_activity_list')(
        context, {'id': dataset_name})
    num_activities = len(package_activity_stream)
    if not num_activities:
        print('  No activities')

    context['for_view'] = True
    for i, activity in enumerate(package_activity_stream):
        # e.g. activity =
        # {'activity_type': u'changed package',
        #  'id': u'62107f87-7de0-4d17-9c30-90cbffc1b296',
        #  'object_id': u'7c6314f5-c70b-4911-8519-58dc39a8e340',
        #  'revision_id': u'c3e8670a-f661-40f4-9423-b011c6a3a11d',
        #  'timestamp': '2018-04-20T16:11:45.363097',
        #  'user_id': u'724273ac-a5dc-482e-add4-adaf1871f8cb'}
        print '  activity {}/{} {}'.format(
            i + 1, num_activities, activity['timestamp'])

        # get the dataset as it was at this revision
        context['revision_id'] = activity['revision_id']
        # call package_show just as we do in activity_stream_item(), only
        # with a revision_id
        dataset = logic.get_action('package_show')(
            context, {'id': activity['object_id'], 'include_tracking': True})
        # get rid of revision_timestamp, which wouldn't be there if saved by
        # during activity_stream_item() - something to do with not specifying
        # revision_id.
        if 'revision_timestamp' in (dataset.get('organization') or {}):
            del dataset['organization']['revision_timestamp']
        for res in dataset['resources']:
            if 'revision_timestamp' in res:
                del res['revision_timestamp']

        actor = model.Session.query(model.User).get(activity['user_id'])
        actor_name = actor.name if actor else activity['user_id']

        # add the data to the Activity, just as we do in activity_stream_item()
        data = {
            'package': dataset,
            'actor': actor_name,
        }
        # there are no action functions for Activity, and anyway the ORM would
        # be faster
        activity_obj = model.Session.query(model.Activity).get(activity['id'])
        if 'resources' in activity_obj.data.get('package', {}):
            print '    Full dataset already recorded - no action'
        else:
            activity_obj.data = data
            # print '    {} dataset {}'.format(actor_name, repr(dataset))
    if model.Session.dirty:
        model.Session.commit()
        print '  saved'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(usage=__doc__)
    parser.add_argument('-c', '--config', help='CKAN config file (.ini)')
    parser.add_argument('--dataset', help='just migrate this particular '
                        'dataset - specify its name')
    args = parser.parse_args()
    assert args.config, 'You must supply a --config'
    from ckan.lib.cli import load_config
    print 'Loading config'
    load_config(args.config)
    if not args.dataset:
        migrate_all_datasets()
    else:
        migrate_dataset(args.dataset)
