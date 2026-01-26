from fields import Fields

def get_choices(sel, path=None, targets=None):
    if path is None:
        path = []
    if targets is None:
        targets = [Fields.OCTET_STRING]
    choice_paths = []
    if hasattr(sel, 'TYPE'):
        if sel.TYPE == 'CHOICE':
            for ident, comp in sel._cont.items():
                sub_paths = get_choices(comp, path + [ident], targets)
                for c, p, t in sub_paths:
                    choice_paths.append(([ident]+c, p, t))
        elif sel.TYPE in ('SEQUENCE', 'SET', 'CLASS'):
            for ident, comp in sel._cont.items():
                choice_paths += get_choices(comp, path + [ident], targets)
        elif sel.TYPE == 'SEQUENCE OF':
            choice_paths += get_choices(sel._cont, path + ['_item_'], targets)
        elif sel.TYPE == 'OCTET STRING' and Fields.OCTET_STRING in targets:
            choice_paths.append(([], path, Fields.OCTET_STRING))
        elif sel.TYPE == 'BIT STRING' and Fields.BIT_STRING in targets:
            choice_paths.append(([], path, Fields.BIT_STRING))
        elif sel.TYPE == 'INTEGER' and Fields.INTEGER in targets:
            choice_paths.append(([], path, Fields.INTEGER))
    return choice_paths
