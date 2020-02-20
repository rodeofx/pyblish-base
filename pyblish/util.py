"""Convenience functions for general publishing"""

from __future__ import absolute_import

# Standard library
import logging
import warnings

# Local library
from . import api, logic, plugin, lib

log = logging.getLogger("pyblish.util")

__all__ = [
    "publish",
    "collect",
    "validate",
    "extract",
    "integrate",

    # Iterator counterparts
    "publish_iter",
    "collect_iter",
    "validate_iter",
    "extract_iter",
    "integrate_iter",
]


def publish(context=None, plugins=None, targets=None, orders=None):
    """Publish everything

    This function will process all available plugins of the
    currently running host, publishing anything picked up
    during collection.

    Arguments:
        context (Context, optional): Context, defaults to
            creating a new context
        plugins (list, optional): Plug-ins to include,
            defaults to results of discover()
        targets (list, optional): Targets to include for publish session.
        orders (list, optional): Orders to process (e.g. [CollectorOrder]).

    Returns:
        Context: The context processed by the plugins.

    Usage:
        >> context = plugin.Context()
        >> publish(context)     # Pass..
        >> context = publish()  # ..or receive a new

    """

    context = context if context is not None else api.Context()

    for _ in publish_iter(context, plugins, targets, orders):
        pass

    return context


def publish_iter(context=None, plugins=None, targets=None, orders=None):
    """Publish iterator

    This function will process all available plugins of the
    currently running host, publishing anything picked up
    during collection.

    Arguments:
        context (Context, optional): Context, defaults to
            creating a new context
        plugins (list, optional): Plug-ins to include,
            defaults to results of discover()
        targets (list, optional): Targets to include for publish session.
        orders (list, optional): Orders to process (e.g. [CollectorOrder]).

    Yields:
        dict: A dictionary that contains all the result information of a
            processed plugin.

    Usage:
        >> context = plugin.Context()
        >> for result in util.publish_iter(context):
               print result
        >> for result in util.publish_iter():
               print result

    """
    for result in _convenience_iter(context, plugins, targets, orders):
        yield result

    api.emit("published", context=context)


def _convenience_iter(context=None, plugins=None, targets=None, orders=None):
    targets = targets or ["default"]
    registered_targets = api.registered_targets()

    # Must check against None, as objects be emptys
    context = api.Context() if context is None else context
    plugins = api.discover() if plugins is None else plugins

    # Register targets
    for target in targets:
        api.register_target(target)

    # Mutable state, used in Iterator
    state = {
        "nextOrder": None,
        "ordersWithError": set()
    }

    # Do not consider inactive plug-ins
    plugins = list(plug for plug in plugins if plug.active)

    # Do not consider plug-ins that are not in any of the given orders
    if orders:
        plugins = list(
            plug for plug in plugins
            if any(lib.inrange(plug.order, order) for order in orders)
        )

    # Keep track of the progress using the same dictionary instance
    progress = {
        "current": 0,
        "total": len(plugins)
    }

    # Process pre-collectors
    precollectors = list(
        plug for plug in plugins
        if plug.order < api.CollectorOrder
        and not lib.inrange(plug.order, api.CollectorOrder)
    )

    for result in _process_plugins(context, precollectors, state, progress):
        yield result

    # Process collectors
    collectors = list(
        plug for plug in plugins
        if lib.inrange(plug.order, api.CollectorOrder)
    )

    if not orders or api.CollectorOrder in orders:
        for result in _process_plugins(context, collectors, state, progress):
            yield result

        api.emit("collected", context=context)

    # Process validators
    validators = list(
        plug for plug in plugins
        if lib.inrange(plug.order, api.ValidatorOrder)
    )

    if not orders or api.ValidatorOrder in orders:
        for result in _process_plugins(context, validators, state, progress):
            yield result

        api.emit("validated", context=context)

    # Process extractors
    extractors = list(
        plug for plug in plugins
        if lib.inrange(plug.order, api.ExtractorOrder)
    )

    if not orders or api.ExtractorOrder in orders:
        for result in _process_plugins(context, extractors, state, progress):
            yield result

        api.emit("extracted", context=context)

    # Process integrators
    integrators = list(
        plug for plug in plugins
        if lib.inrange(plug.order, api.IntegratorOrder)
    )

    if not orders or api.IntegratorOrder in orders:
        for result in _process_plugins(context, integrators, state, progress):
            yield result

        api.emit("integrated", context=context)

    # Process post-integrators
    postintegrators = list(
        plug for plug in plugins
        if plug.order > api.IntegratorOrder
        and not lib.inrange(plug.order, api.IntegratorOrder)
    )

    for result in _process_plugins(context, postintegrators, state, progress):
        yield result

    # Deregister targets
    for target in targets:
        if target not in registered_targets:
            api.deregister_target(target)


def _process_plugins(context, plugins, state, progress):
    expected_plugins_count = len(plugins)
    actual_plugins_count = 0
    processed_plugins = set()

    for plug, instance in logic.Iterator(plugins, context, state):
        # Do not consider instances when tracking progress
        if plug not in processed_plugins:
            processed_plugins.add(plug)
            actual_plugins_count += 1
            progress["current"] += 1

        result = plugin.process(plug, context, instance)

        # Make note of the order at which the error occurred
        if result["error"]:
            state["ordersWithError"].add(plug.order)

        error = result["error"]
        if error is not None:
            print(error)

        result["progress"] = float(progress["current"]) / progress["total"]

        yield result

    # If some plugins were skipped, add difference to progress
    progress["current"] += expected_plugins_count - actual_plugins_count


def collect(context=None, plugins=None, targets=None):
    """Convenience function for collection-only

     _________    . . . . .  .   . . . . . .   . . . . . . .
    |         |   .          .   .         .   .           .
    | Collect |-->. Validate .-->. Extract .-->. Integrate .
    |_________|   . . . . .  .   . . . . . .   . . . . . . .

    """

    context = context if context is not None else api.Context()
    for result in collect_iter(context, plugins, targets):
        pass

    return context


def validate(context=None, plugins=None, targets=None):
    """Convenience function for validation-only

    . . . . . .    __________    . . . . . .   . . . . . . .
    .         .   |          |   .         .   .           .
    . Collect .-->| Validate |-->. Extract .-->. Integrate .
    . . . . . .   |__________|   . . . . . .   . . . . . . .

    """

    context = context if context is not None else api.Context()
    for result in validate_iter(context, plugins, targets):
        pass

    return context


def extract(context=None, plugins=None, targets=None):
    """Convenience function for extraction-only

    . . . . . .   . . . . .  .    _________    . . . . . . .
    .         .   .          .   |         |   .           .
    . Collect .-->. Validate .-->| Extract |-->. Integrate .
    . . . . . .   . . . . .  .   |_________|   . . . . . . .

    """

    context = context if context is not None else api.Context()
    for result in extract_iter(context, plugins, targets):
        pass

    return context


def integrate(context=None, plugins=None, targets=None):
    """Convenience function for integration-only

    . . . . . .   . . . . .  .   . . . . . .    ___________
    .         .   .          .   .         .   |           |
    . Collect .-->. Validate .-->. Extract .-->| Integrate |
    . . . . . .   . . . . .  .   . . . . . .   |___________|

    """

    context = context if context is not None else api.Context()
    for result in integrate_iter(context, plugins, targets):
        pass

    return context


def collect_iter(context=None, plugins=None, targets=None):
    """ Convenience iterator for collection-only

    This function will process only the collector plug-ins.

    Arguments:
        context (Context, optional): Context, defaults to
            creating a new context
        plugins (list, optional): Plug-ins to include,
            defaults to results of discover()
        targets (list, optional): Targets to include for publish session.

    Yields:
        dict: A dictionary that contains all the result information of a
            processed plugin.

    Usage:
        >> context = plugin.Context()
        >> for result in util.collect_iter(context):
               print result
    """
    for result in _convenience_iter(
            context, plugins, targets, orders=[api.CollectorOrder]
    ):
        yield result


def validate_iter(context=None, plugins=None, targets=None):
    """ Convenience iterator for validation-only

    This function will process only the validator plug-ins.

    Arguments:
        context (Context, optional): Context, defaults to
            creating a new context
        plugins (list, optional): Plug-ins to include,
            defaults to results of discover()
        targets (list, optional): Targets to include for publish session.

    Yields:
        dict: A dictionary that contains all the result information of a
            processed plugin.

    Usage:
        >> context = plugin.Context()
        >> util.collect(context)
        >> for result in util.validate_iter(context):
               print result
    """
    for result in _convenience_iter(
            context, plugins, targets, orders=[api.ValidatorOrder]):
        yield result


def extract_iter(context=None, plugins=None, targets=None):
    """ Convenience iterator for extraction-only

    This function will process only the extractor plug-ins.

    Arguments:
        context (Context, optional): Context, defaults to
            creating a new context
        plugins (list, optional): Plug-ins to include,
            defaults to results of discover()
        targets (list, optional): Targets to include for publish session.

    Yields:
        dict: A dictionary that contains all the result information of a
            processed plugin.

    Usage:
        >> context = plugin.Context()
        >> util.collect(context)
        >> util.validate(context)
        >> for result in util.extract_iter(context):
               print result
    """
    for result in _convenience_iter(
            context, plugins, targets, orders=[api.ExtractorOrder]
    ):
        yield result


def integrate_iter(context=None, plugins=None, targets=None):
    """ Convenience iterator for integration-only

    This function will process only the integrator plug-ins.

    Arguments:
        context (Context, optional): Context, defaults to
            creating a new context
        plugins (list, optional): Plug-ins to include,
            defaults to results of discover()
        targets (list, optional): Targets to include for publish session.

    Yields:
        dict: A dictionary that contains all the result information of a
            processed plugin.

    Usage:
        >> context = plugin.Context()
        >> util.collect(context)
        >> util.validate(context)
        >> util.extract(context)
        >> for result in util.integrate_iter(context):
               print result
    """
    for result in _convenience_iter(
            context, plugins, targets, orders=[api.IntegratorOrder]
    ):
        yield result


def _convenience(context=None, plugins=None, targets=None, orders=None):
    context = context if context is not None else api.Context()

    for _ in _convenience_iter(context, plugins, targets, orders):
        pass

    return context


# Backwards compatibility
select = collect
conform = integrate
run = publish  # Alias


def publish_all(context=None, plugins=None):
    warnings.warn("pyblish.util.publish_all has been "
                  "deprecated; use publish()")
    return publish(context, plugins)


def validate_all(context=None, plugins=None):
    warnings.warn("pyblish.util.validate_all has been "
                  "deprecated; use collect() followed by validate()")
    context = collect(context, plugins)
    return validate(context, plugins)
