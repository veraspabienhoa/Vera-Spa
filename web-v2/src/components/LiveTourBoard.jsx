import { memo, useRef, useCallback } from 'react'
import UiCustomText from "../components/UiCustomText";
import { breakCellValue } from "../lib/liveTourBreaktime";
function LiveTourBoard({
  allDisplayedSelected,
  appearanceTableColumns,
  appointmentColumn,
  appointmentEditor,
  busy,
  actionBusy,
  allowStartOutsideShift,
  canBook,
  canEditAppointment,
  canOperate,
  canPayment,
  cellValue,
  clockMs,
  columnClass,
  columns,
  data,
  displayedRecords,
  employeeColumn,
  employeeServiceActions,
  hasGroup,
  openEmployeeAndShift,
  recordId,
  rowClass,
  selectedIds,
  statusColumn,
  sttColumn,
  toggleDisplayed,
  toggleRow
}) {
  const callbacks=useRef({appointmentEditor,employeeServiceActions,openEmployeeAndShift,toggleRow})
  callbacks.current={appointmentEditor,employeeServiceActions,openEmployeeAndShift,toggleRow}
  const renderAppointment=useCallback((...args)=>callbacks.current.appointmentEditor(...args),[])
  const renderActions=useCallback((...args)=>callbacks.current.employeeServiceActions(...args),[])
  const openEmployee=useCallback((...args)=>callbacks.current.openEmployeeAndShift(...args),[])
  const selectRow=useCallback((...args)=>callbacks.current.toggleRow(...args),[])
  const renderVersion=JSON.stringify([appearanceTableColumns,columns,employeeColumn,appointmentColumn,statusColumn,canBook,canEditAppointment,canOperate,canPayment,clockMs,data.revision,data.payment_settings?.shift_ready_times,actionBusy,allowStartOutsideShift])
  return <section data-ui-key="u-7a0401d60a37" className="panel tour-table-panel tour-records-panel">
      <div className="responsive-data-table tour-table" tabIndex="0" aria-label="Danh sách Live Tour"><table data-ui-key="u-ecfc5f45a158"><thead><tr>{appearanceTableColumns.map(entry => entry.kind === 'select' ? <th data-ui-key="u-60b4eb9caa75" className="live-tour-select-col" data-appearance-key="Ô chọn" key="__select"><input type="checkbox" checked={allDisplayedSelected} onChange={toggleDisplayed} aria-label="Chọn tất cả nhân viên đang hiển thị" /></th> : entry.kind === 'actions' ? <th data-ui-key="u-231630a4deef" data-ui-label-default="Thao tác" className="live-tour-actions-col" data-appearance-key="Thao tác" key="__actions"><UiCustomText uiKey="u-231630a4deef">Thao tác</UiCustomText></th> : <th data-ui-key="u-afa8220f3244" className={columnClass(entry.column)} data-appearance-key={entry.key} key={entry.column}>{entry.column}</th>)}</tr></thead><tbody>{displayedRecords.map((item, index) => {
            const id = recordId(item, index);
            return <EmployeeRow key={id} item={item} index={index} id={id} appearanceTableColumns={appearanceTableColumns} appointmentColumn={appointmentColumn} canBook={canBook} canEditAppointment={canEditAppointment} canOperate={canOperate} canPayment={canPayment} cellValue={cellValue} clockMs={clockMs} columnClass={columnClass} columns={columns} employeeColumn={employeeColumn} hasGroup={hasGroup} rowClass={rowClass} statusColumn={statusColumn} sttColumn={sttColumn} selected={selectedIds.has(id)} shiftReadyTimes={data.payment_settings?.shift_ready_times} appointmentEditor={renderAppointment} employeeServiceActions={renderActions} openEmployeeAndShift={openEmployee} toggleRow={selectRow} renderVersion={renderVersion}/>;
          })}</tbody></table></div>
      {!busy && !displayedRecords.length && <div className="setup-note">Không có nhân viên phù hợp với ca/bộ lọc đang chọn.</div>}
    </section>;
}
export default LiveTourBoard;

const EmployeeRow = memo(function EmployeeRow({item,index,id,selected,appearanceTableColumns,appointmentColumn,appointmentEditor,canBook,canEditAppointment,canOperate,canPayment,cellValue,clockMs,columnClass,columns,employeeColumn,employeeServiceActions,hasGroup,openEmployeeAndShift,rowClass,statusColumn,sttColumn,toggleRow,shiftReadyTimes}) { return <tr className={rowClass(item, selected, shiftReadyTimes, clockMs)} onClick={event => {
              if (!event.target.closest('button,input,a,select')) toggleRow(id);
            }}>{appearanceTableColumns.map(entry => {
                if (entry.kind === 'select') return <td className="live-tour-select-col" data-appearance-key="Ô chọn" key="__select"><input type="checkbox" checked={selected} onChange={() => toggleRow(id)} aria-label={`Chọn ${cellValue(item, employeeColumn)}`} /></td>;
                if (entry.kind === 'actions') return <td className="live-tour-actions-col" data-appearance-key="Thao tác" key="__actions">{employeeServiceActions(item)}</td>;
                const column = entry.column;
                return <td className={columnClass(column)} data-appearance-key={entry.key} key={column}>{column === employeeColumn ? <button data-ui-key="u-b1ca0bd563d7" type="button" className="text-button" title={String(item[column] ?? '')} disabled={!canOperate && !canPayment && !canBook} onClick={() => openEmployeeAndShift(item, index)}>{String(item[column] ?? '')}</button> : column === appointmentColumn && canEditAppointment ? appointmentEditor(item) : column === sttColumn(columns) ? String(item[column] ?? '') : column === statusColumn && hasGroup(item, 'doing') ? 'Thực hiện' : String(breakCellValue(item, column, clockMs))}</td>;
              })}</tr> }, (before,after)=>before.renderVersion===after.renderVersion && before.selected===after.selected && before.index===after.index && JSON.stringify(before.item)===JSON.stringify(after.item))
