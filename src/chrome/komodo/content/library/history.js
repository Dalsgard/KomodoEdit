/* ***** BEGIN LICENSE BLOCK *****
 * Version: MPL 1.1/GPL 2.0/LGPL 2.1
 * 
 * The contents of this file are subject to the Mozilla Public License
 * Version 1.1 (the "License"); you may not use this file except in
 * compliance with the License. You may obtain a copy of the License at
 * http://www.mozilla.org/MPL/
 * 
 * Software distributed under the License is distributed on an "AS IS"
 * basis, WITHOUT WARRANTY OF ANY KIND, either express or implied. See the
 * License for the specific language governing rights and limitations
 * under the License.
 * 
 * The Original Code is Komodo code.
 * 
 * The Initial Developer of the Original Code is ActiveState Software Inc.
 * Portions created by ActiveState Software Inc are Copyright (C) 2000-2009
 * ActiveState Software Inc. All Rights Reserved.
 * 
 * Contributor(s):
 *   ActiveState Software Inc
 * 
 * Alternatively, the contents of this file may be used under the terms of
 * either the GNU General Public License Version 2 or later (the "GPL"), or
 * the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
 * in which case the provisions of the GPL or the LGPL are applicable instead
 * of those above. If you wish to allow use of your version of this file only
 * under the terms of either the GPL or the LGPL, and not to allow others to
 * use your version of this file under the terms of the MPL, indicate your
 * decision by deleting the provisions above and replace them with the notice
 * and other provisions required by the GPL or the LGPL. If you do not delete
 * the provisions above, a recipient may use your version of this file under
 * the terms of any one of the MPL, the GPL or the LGPL.
 * 
 * ***** END LICENSE BLOCK ***** */

/* UI-side handler for Komodo history functionality.
 *
 * Contents:
 * 1. Wrappers around the koHistory service
 * 2. Controller for handling the forward and back commands
 * 3. Methods to implement the controller commands.
 */

xtk.include('controller');

if (typeof(ko)=='undefined') {
    var ko = {};
}

ko.history = {};
(function() {

const _SKIP_DBGP_FALLBACK_LIMIT = 100; //XXX Add invisible pref history_fallback_limit
    
var _log = ko.logging.getLogger('history');

var _bundle = Components.classes["@mozilla.org/intl/stringbundle;1"]
    .getService(Components.interfaces.nsIStringBundleService)
    .createBundle("chrome://komodo/locale/views.properties");
    
function HistoryController() {
    this.historySvc = Components.classes["@activestate.com/koHistoryService;1"].
                getService(Components.interfaces.koIHistoryService);
    window.controllers.appendController(this);
    window.updateCommands("history_changed");
}

HistoryController.prototype = new xtk.Controller();
HistoryController.prototype.constructor = HistoryController;
HistoryController.prototype.destructor = function() { };

HistoryController.prototype.is_cmd_historyForward_supported = function() {
    return true;
};
HistoryController.prototype.is_cmd_historyForward_enabled = function() {
    return this.historySvc.can_go_forward();
};

HistoryController.prototype.do_cmd_historyForward = function() {
    if (!this.historySvc.can_go_forward()) {
        // keybindings don't go through the is-enabled test.
        return;
    }
    ko.history.history_forward(1);
};

HistoryController.prototype.is_cmd_historyBack_supported = function() {
    return true;
};
HistoryController.prototype.is_cmd_historyBack_enabled = function() {
    return this.historySvc.can_go_back();
};

HistoryController.prototype.do_cmd_historyBack = function() {
    if (!this.historySvc.can_go_back()) {
        // keybindings don't go through the is-enabled test.
        return;
    }
    ko.history.history_back(1);
};

HistoryController.prototype.is_cmd_historyRecentLocations_supported = function() {
    return true;
};
HistoryController.prototype.is_cmd_historyRecentLocations_enabled = function() {
    return this.historySvc.have_recent_history();
};

function _appCommandEventHandler(evt) {
    // Handle the browser-back and browser-forward application-specific
    // buttons on supported mice.  Mozilla forwards these
    // as "AppCommand" events.
    // From KD 218, referencing browser/base/content/browser.js
    switch (evt.command) {
        case "Back":
            if (_controller.historySvc.can_go_back()) {
                ko.history.history_back(1);
            }
            break;
        case "Forward":
            if (_controller.historySvc.can_go_forward()) {
                ko.history.history_forward(1);
            }
            break;
    }
};

function UnloadableLocError() {}
UnloadableLocError.prototype = new Error();
        
this.init = function() {
    this._observerSvc = Components.classes["@mozilla.org/observer-service;1"].
                getService(Components.interfaces.nsIObserverService);
    this._observerSvc.addObserver(this, 'history_changed', false);
    ko.main.addWillCloseHandler(this.destroy, this);
    window.updateCommands('history_changed');
    window.addEventListener("AppCommand", _appCommandEventHandler, true);
};

this.destroy = function() {
    this._observerSvc.removeObserver(this, 'history_changed', false);
    window.removeEventListener("AppCommand", _appCommandEventHandler, true);
};

this.observe = function(subject, topic, data) {
    // Unless otherwise specified the 'subject' is the view, and 'data'
    // arguments are expected to be empty for all notifications.
    if (topic == 'history_changed') {
        window.updateCommands('history_changed');
    }
};


/**
 * Get the current location.
 *
 * @param view {view} An optional view in which to get the current location.
 *      If not given the current view is used.
 * @returns {koILocation} or null if could not determine a current loc.
 */
function _get_curr_loc(view /* =current view */) {
    if (typeof(view) == "undefined" || view == null) {
        view = ko.views.manager.currentView;
    }
    var loc = null;
    if (!view) {
        // pass
    } else if (view.getAttribute("type") == "editor") {
        loc = _controller.historySvc.editor_loc_from_info(
            window._koNum,
            view.tabbedViewId,
            view);
    } else {
        _log.warn("cannot get current location for '"
                  +view.getAttribute("type")+"' view: "+view);
    }
    return loc;
};


/**
 * Note the current location.
 *
 * @param view {view} An optional view in which to get the current location.
 *      If not given the current view is used.
 * @returns {koILocation} The noted location (or null if could not determine
 *      a current loc).
 */
this.note_curr_loc = function note_curr_loc(view, /* = currentView */
                                            check_section_change /* false */
                                            ) {
    if (typeof(view) == "undefined" || view == null) view = ko.views.manager.currentView;
    if (typeof(check_section_change) == "undefined") check_section_change = false;
    var loc = _get_curr_loc(view);
    if (!loc) {
        return null;
    }
    return _controller.historySvc.note_loc(loc, check_section_change, view);
};

/** 
 * Returns the view and line # based on the loc.
 *
 * @param loc {Location}.
 * @param handle_view_line_callback {Function}.
 * @param open_if_needed {Boolean}.
 * @returns undefined
 *
 * This function might open a file asynchronously, so it invokes
 * handle_view_line_callback to do the rest of the work.
 */
function view_and_line_from_loc(loc, handle_view_line_callback,
                                open_if_needed/*=true*/
                                ) {
    if (typeof(open_if_needed) == "undefined") open_if_needed = true;
    var uri = loc.uri;
    if (!uri) {
        _log.error("go_to_location: given empty uri");
        return null;
    }
    var lineNo = loc.line;
    var window_num = loc.window_num;
    
    var view = (open_if_needed
                ? ko.windowManager.getViewForURI(uri, window_num, loc.tabbed_view_id)
                : ko.windowManager.getViewForURI(uri));
    if (view && open_if_needed) {
        // See if we're switching windows.
        var currentView = ko.views.manager.currentView;
        if (!currentView || currentView.ownerDocument != view.ownerDocument) {
            view.ownerDocument.defaultView.window.focus();
        }
    }
    var is_already_open = (view != null);
    function local_callback(view_) {
        if (is_already_open) {
            var betterLineNo = view_.scimoz.markerLineFromHandle(loc.marker_handle);
            if (betterLineNo != -1) {
                lineNo = betterLineNo;
            }
        }
        return handle_view_line_callback(view_, lineNo);
    }
    if (!view) {
        if (open_if_needed) {
            if (uri.indexOf("dbgp://") == 0) {
                throw new UnloadableLocError("unloadable");
            }
        } else {
            return handle_view_line_callback(null, lineNo);
        }
        function callback(view_) {
            if (!view_)  {
                ko.statusBar.AddMessage(
                    "Can't find file " + uri,
                    "editor", 5000, false);
                return null;
            }
            return handle_view_line_callback(view_, lineNo);
        };
        // Open in the correct window + multi-view
        // Never open a new window -- if the marked window
        // is gone, use the current window.
        //
        var win = ko.windowManager.windowFromWindowNum(window_num);
        var wko = win ? win.ko : ko;
        view = wko.views.manager.doFileOpenAtLineAsync(uri, lineNo,
                                                       null, // viewType='editor'
                                                       null, // viewList=null
                                                       null, // index=-1
                                                       callback);
    }
    return local_callback(view);
}

this.go_to_location = function go_to_location(loc) {
    //XXX Use window and view IDs
    var view_type = loc.view_type;
    if (view_type != "editor") {
        throw new Error("history: goto location of type " + view_type
                        + " not yet implemented.");
    }
    function _callback(view, lineNo) {
        if (!view) return;
        var scimoz = view.scimoz;
        view.makeCurrent();
        var targetPos = scimoz.positionFromLine(lineNo) + loc.col;
        scimoz.currentPos = scimoz.anchor = targetPos;
        scimoz.gotoPos(targetPos);
        window.updateCommands("history_changed");
    }
    view_and_line_from_loc(loc, _callback, true);
};

const _dbgp_url_stripper = new RegExp('^dbgp://[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}/');

function labelFromLoc(loc) {
    var baseName = null, view, lineNo;
    function _callback(view, lineNo) {
        lineNo += 1;
        var dirName = null;
        var finalLabel, label, tooltiptext;
        try {
            if (view) {
                var labels = ko.views.labelsFromView(view, lineNo);
                if (labels[0]) {
                    return labels[0];
                }
            }
            var koFileEx = Components.classes["@activestate.com/koFileEx;1"]
                             .createInstance(Components.interfaces.koIFileEx);
            koFileEx.URI = loc.uri;
            switch (koFileEx.scheme) {
            case "file":
                dirName = koFileEx.dirName;
                baseName = koFileEx.baseName;
                break;
            case "dbgp":
                baseName = loc.uri.replace(_dbgp_url_stripper, "dbgp:///");
                break;
            default:
                baseName = loc.uri;
            }
        } catch(ex) {
            _log.exception("labelFromLoc: " + ex + "\n");
            baseName = loc.uri;
        }
        var finalLabel = baseName + ":" + lineNo;
        if (dirName) {
            finalLabel += " (" + dirName + ")";
        }
        return finalLabel;
    }
    // This is a sync call (not async), but it's coded this way
    // so go_to_location can share common code. 
    return view_and_line_from_loc(loc, _callback, false); // don't open closed views
}

this.initPopupMenuRecentLocations = function(event) {
    try {
    var popupMenu = event.target;
    while (popupMenu.hasChildNodes()) {
        popupMenu.removeChild(popupMenu.lastChild);
    }
    var locList = {};
    var currentLocIdx = {};
    _controller.historySvc.get_recent_locs(_get_curr_loc(),
                                               currentLocIdx, locList, {});
    currentLocIdx = currentLocIdx.value;
    locList = locList.value;
    
    var menuitem, loc;
    for (var i = 0; i < locList.length; ++i) {
        loc = locList[i];
        if (!loc) {
            // Null items can come from unhandled views, like the startPage
            continue;
        }
        var tooltip;
        var label = labelFromLoc(loc);
        if (!label) {
            // Don't display unloaded unloaded dbgp URIs in the dropdown.
            // Otherwise they show up as blank lines.
            continue;
        }
        menuitem = document.createElement("menuitem");
        menuitem.setAttribute("label", label);
        menuitem.setAttribute("index", 0);
        var handler = null;
        var delta = currentLocIdx - i;
        if (delta == 0) {
            menuitem.setAttribute("class", "history-nav-current");
            menuitem.setAttribute("type", "checkbox");
            menuitem.setAttribute("checked", "true");
            handler = "event.stopPropagation()";
            tooltip = _bundle.GetStringFromName("historyStayAtCurrentLocation");
        } else if (delta > 0) {
            // move forward, with explicit=true
            handler = "ko.history.history_forward(" + delta + ", true)";
            tooltip = _bundle.GetStringFromName("historyGoForwardToThisLocation");
        } else {
            // move back, with explicit=true
            handler = "ko.history.history_back(" + (-1 * delta) + ", true)";
            tooltip = _bundle.GetStringFromName("historyGoBackToThisLocation");
        }
        menuitem.setAttribute("tooltiptext", tooltip);
        menuitem.setAttribute("oncommand", handler);
        popupMenu.appendChild(menuitem);
    }
    } catch(ex) {
        _log.exception("initPopupMenuRecentLocations: " + ex);
    }
};

this._history_move = function(go_method_name, check_method_name, delta,
                              explicit) {
    // @param go_method_name {String} either 'go_back' or 'go_forward',
    //        used to make this routine work for both directins.
    // @param check_method_name {String} either 'can_go_back' or 'can_go_forward',
    //        Same rationale as go_method_name
    // @param delta {Integer} # of hops to make
    // @param explicit {Boolean} if true, the user pressed the "Recent
    //        Locations" button.  Otherwise they hit the go_back
    //        or go_forward command.

    if (typeof(explicit) == "undefined") explicit=false;
    var curr_loc = _get_curr_loc();
    var is_moving_back = (go_method_name == 'go_back');
    for (var i = 0; i < _SKIP_DBGP_FALLBACK_LIMIT; i++) {
        var loc = _controller.historySvc[go_method_name](curr_loc, delta);
        try {
            this.go_to_location(loc);
            return;
        } catch(ex if ex instanceof UnloadableLocError) {
            // Don't remove the curr_loc if we're no longer next to it.
            _controller.historySvc.obsolete_uri(loc.uri, delta, is_moving_back);
            if (!_controller.historySvc[check_method_name]()) {
                window.updateCommands("history_changed");
                break;
            }
            if (explicit) {
                break;
            }
            // assert delta == 1
            
            // We hit an obsolete URI on an arrow command.
            // Keep going in the same direction until we either
            // reach a valid URI, the end, or hit the fallback limit.
        }
    }
    var msg1;
    if (explicit) {
        msg1 = _bundle.formatStringFromName("temporaryBufferNoLongerAccessible.templateFragment",
                                          [loc.uri], 1);
    } else if (i == _SKIP_DBGP_FALLBACK_LIMIT) {
        msg1 = _bundle.formatStringFromName("historyRanIntoSequence.templateFragment",
                                          [_SKIP_DBGP_FALLBACK_LIMIT], 1);
    } else {
        msg1 = _bundle.GetStringFromName("historyRemainingLocationsAreObsolete.fragment");
    }
    var msg2 = _bundle.formatStringFromName(is_moving_back
                                         ? "historyCouldntMoveBack.template"
                                         : "historyCouldntMoveForward.template",
                                         [msg1], 1);
    ko.statusBar.AddMessage(msg2, "editor", 3000, true);
};

this.history_back = function(delta, explicit) {
    this._history_move('go_back', 'can_go_back', delta, explicit);
};

this.history_forward = function(delta, explicit) {
    this._history_move('go_forward', 'can_go_forward', delta, explicit);
};

var _controller = new HistoryController();
}).apply(ko.history);

