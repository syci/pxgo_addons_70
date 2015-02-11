# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Pexego Sistemas Informáticos (http://www.pexego.es) All Rights Reserved
#    $Jesús Ventosinos Mayor$
#    $Javier Colmenero Fernández$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import time
from datetime import datetime, date
from openerp import tools
from tools.translate import _
from osv import fields, osv
import openerp.exceptions

_TASK_STATE = [('draft', 'New'),('open', 'In Progress'),('working', 'Working') ,('pending', 'Pending'), ('done', 'Done'), ('cancelled', 'Cancelled')]


class project_task_type(osv.osv):
    _inherit = 'project.task.type'

    _columns = {
        'state': fields.selection(_TASK_STATE, 'Related Status', required=True,
                        help="The status of your document is automatically changed regarding the selected stage. " \
                            "For example, if a stage is related to the status 'Close', when your document reaches this stage, it is automatically closed."),
    }

class project_task_history(osv.osv):
    _inherit = "project.task.history"
    _columns = {
         'state': fields.selection([('draft', 'New'),('open', 'In Progress'),('pending', 'Pending'), ('done', 'Done'), ('working', 'Working') ,('cancelled', 'Cancelled')], 'State', readonly=True, required=True)
    }
project_task_history()

class time_control_user_task(osv.osv):
    _name = 'time.control.user.task'
    _columns = {
         'user':fields.many2one('res.users','user'),
         'work_start': fields.datetime('Work start'),
         'work_end': fields.datetime('Work end'),
         'started_task':fields.many2one('project.task', 'Started task')
    }
time_control_user_task()

class project_task(osv.osv):

    def _get_users_working(self, cr, uid, ids, field_name, args, context=None):
        if context is None:
            context = {}
        res = {}
        tasks = self.pool.get("project.task").browse(cr, uid, ids)
        for task in tasks:
            stream = ''
            user_task_ids = self.pool.get("time.control.user.task").search(cr,uid,[('started_task', '=', task.id)])
            user_in_task =  self.pool.get("time.control.user.task").browse(cr, uid, user_task_ids)
            if user_in_task:
                for usr in user_in_task:
                    if usr.user.name != None:
                        stream+=usr.user.name+u","
                res[task.id] = stream
            else:
                res[task.id] = False
        return res

    _inherit = "project.task"
    _columns = {
        'other_users_ids': fields.many2many('res.users', 'project_task_user_rel', 'user_id', 'task_id', 'Other users'),
        'working_users': fields.function(_get_users_working, method=True, string='Working users', type='char', size=255)
     }

    def stop_task(self,cr,uid,task_id,final,user_task,context=None):
        if context is None:
            context = {}
        self.pool.get('time.control.user.task').write(cr, uid, user_task.id, {'work_end':final})
        user_task = self.pool.get('time.control.user.task').browse(cr,uid,user_task.id)
        #Call wizard:
        wizard_id = self.pool.get("task.time.control.confirm.wizard").create(cr, uid, {'task_to_start':task_id,'user_task':user_task.id}, context=context)
        return {
            'name':_("Confirm Time"),
            'view_mode': 'form',
            'view_id': False,
            'view_type': 'form',
            'res_model': 'task.time.control.confirm.wizard',
            'res_id':wizard_id,
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'new',
            'domain': '[]',
            'context': context
        }

    def work_start_btn(self,cr,uid,task_id,context):

        #timestamp = datetime.strptime(datetime.now(), tools.DEFAULT_SERVER_DATETIME_FORMAT)
        ts = fields.datetime.context_timestamp(cr, uid, datetime.now(), context)
        start = ts.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        user_task_id = self.pool.get('time.control.user.task').search(cr,uid,[('user', '=', uid)])
        if user_task_id:
            user_task = self.pool.get('time.control.user.task').browse(cr,uid,user_task_id)[0]
            if user_task.started_task:
                if user_task.started_task.id == task_id[0]:
                    raise osv.except_osv(_("Warning !"), _("Task is alredy started."))
                return self.stop_task(cr,uid,task_id[0],start,user_task,context)

            else:
                task = self.pool.get('project.task').browse(cr,uid,task_id)[0]
                if task.state == 'draft':
                    self.do_open(cr, uid, task_id, context)
                ttype = self.pool.get('project.task').stage_find(cr, uid, [task], False, [('state', '=', 'working')], context=context)
                self.pool.get('project.task').write(cr,uid,task_id,{'stage_id': ttype})
                self.pool.get('time.control.user.task').write(cr, uid, user_task_id, {'work_start':start,'started_task':task_id[0]})
        else:
            task = self.pool.get('project.task').browse(cr,uid,task_id)[0]
            if task.state == 'draft':
                self.do_open(cr, uid, task_id, context)
            args={
                'user': uid,
                'work_start':start,
                'started_task':task_id[0]
            }
            self.pool.get('time.control.user.task').create(cr,uid,args)
            ttype = self.pool.get('project.task').stage_find(cr, uid,  [task], False, [('state', '=', 'working')], context=context)
            self.pool.get('project.task').write(cr,uid,task_id,{'stage_id':ttype})
        return True


    def work_end_btn(self,cr,uid,task_id,context):

        #timestamp = datetime.strptime(datetime.now(), tools.DEFAULT_SERVER_DATETIME_FORMAT)
        ts = fields.datetime.context_timestamp(cr, uid, datetime.now(), context)
        end_datetime = ts.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        user_task_id = self.pool.get('time.control.user.task').search(cr,uid,[('user', '=', uid)])
        if user_task_id:
            user_task = self.pool.get('time.control.user.task').browse(cr,uid,user_task_id[0])
            if user_task.started_task.id == task_id[0]:
                finished = self.stop_task(cr,uid,None,end_datetime,user_task,context)
                if finished:
                    return finished
                else:
                    raise osv.except_osv(_("Warning !"),_('Task is not init.'))
            else:
                raise osv.except_osv(_("Warning !"),_('Task init by another user.'))
        return True

project_task()

class project_task_work(osv.osv):
    _inherit = "project.task.work"
    _columns = {
        'work_start': fields.datetime('Work start'),
        'work_end': fields.datetime('Work end')
    }
project_task_work()
