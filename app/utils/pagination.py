from flask import request
from sqlalchemy import or_, desc, asc


def paginate_query(base_query, model, search_fields=None, default_sort=None, serializer_func=None):
    """
    Standard DataTables & server-side pagination processor for SQLAlchemy queries.
    Parameters are extracted safely from Flask request.args.
    Zero raw SQL: all filters use parameterized ORM constructs.

    Returns:
        dict: Standard DataTables JSON response format
              {"draw": int, "recordsTotal": int, "recordsFiltered": int, "data": list}
    """
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 10, type=int)
    search_value = request.args.get('search[value]', '').strip()

    # 1. Total records before filtering
    records_total = base_query.count()

    # 2. Apply search filter across specified model fields
    query = base_query
    if search_value and search_fields:
        search_filter = []
        pattern = f"%{search_value}%"
        for field in search_fields:
            if hasattr(model, field):
                col = getattr(model, field)
                # Safe parameterized ILIKE / LIKE
                search_filter.append(col.ilike(pattern))
        if search_filter:
            query = query.filter(or_(*search_filter))

    # 3. Filtered record count
    records_filtered = query.count()

    # 4. Sorting
    order_column_idx = request.args.get('order[0][column]', type=int)
    order_dir = request.args.get('order[0][dir]', 'asc')

    applied_sort = False
    if order_column_idx is not None:
        col_name = request.args.get(f'columns[{order_column_idx}][data]')
        if col_name and hasattr(model, col_name):
            col_attr = getattr(model, col_name)
            query = query.order_by(desc(col_attr) if order_dir == 'desc' else asc(col_attr))
            applied_sort = True

    if not applied_sort:
        if default_sort is not None:
            query = query.order_by(default_sort)
        elif hasattr(model, 'id'):
            query = query.order_by(model.id.desc())

    # 5. Pagination offset & limit
    if length > 0:
        query = query.offset(start).limit(length)

    items = query.all()

    # 6. Serialization
    if serializer_func:
        data = [serializer_func(item) for item in items]
    elif hasattr(model, 'to_dict'):
        data = [item.to_dict() for item in items]
    else:
        data = []

    return {
        "draw": draw,
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": data
    }
